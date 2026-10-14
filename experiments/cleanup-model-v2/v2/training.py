"""Continue the preserved adapter using the verified prefix-cached MLX loop."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from .common import *


def checked_dataset(dataset):
    freeze = read_json(dataset / "freeze.json")
    if not freeze:
        raise RuntimeError("Evaluation sets must be fixed first")
    if any(file_sha256(dataset / (name + ".jsonl" if name in ("test", "validation") else name)) != digest
           for name, digest in freeze.get("files", {}).items()):
        raise RuntimeError("Frozen dataset file changed")
    if any(file_sha256(ROOT / path) != digest for path, digest in freeze.get("capture_source_hashes", {}).items()):
        raise RuntimeError("Training prompt source changed after capture")
    return freeze


def run(name, count, start=0, control=False, initial_adapter=None, lr=3e-5, dataset_dir=None):
    from lfx import train
    run_dir=ART/"train"/name
    dataset=Path(dataset_dir) if dataset_dir else ART/"dataset"
    initial=Path(initial_adapter) if initial_adapter else Path(c_identity()["adapter_path"])
    if not control:
        checked_dataset(dataset)
    request = {"name":name,"count":count,"start":start,"control":control,"lr":lr,
               "dataset_dir":str(dataset.resolve()),
               "dataset_freeze_sha256":file_sha256(dataset/"freeze.json") if not control else None,
               "initial_adapter":str(initial.resolve()),
               "initial_adapter_sha256":file_sha256(initial/"adapters.safetensors"),
               "training_config":CONFIG["training"]}
    if (run_dir/"completion.json").exists():
        if read_json(run_dir/"request.json") != request:
            raise RuntimeError("Completed training name belongs to another or unrecorded request")
        return read_json(run_dir/"completion.json")
    if (run_dir/"metrics.jsonl").exists():
        raise RuntimeError("Interrupted run retained; use a distinct run name with an explicit initial adapter")
    old_pairs=read_jsonl(OLD_ART/"dataset/train.jsonl")
    verified={p["pair_id"] for p in old_pairs if p.get("verification")=="PASS"}
    old_caps=[p for p in read_jsonl(OLD_ART/"dataset/train_captures.jsonl") if p["pair_id"] in verified]
    rng=random.Random(20261013)
    rng.shuffle(old_caps)
    if control:
        chosen=old_caps[:count]
        validation=read_jsonl(OLD_ART/"dataset/validation_captures.jsonl")
        vexamples=train.load_examples(validation,rng_seed=991)[:100]
    else:
        caps=read_jsonl(dataset/"train_captures.jsonl")
        # Monotone family ids keep nested scaling mixtures stable as later
        # generation waves are appended. The trainer shuffles within this set.
        caps=sorted(caps,key=lambda c:c["family_id"])
        fresh=caps[start:start+count]
        if len(fresh)!=count:
            raise RuntimeError(f"Need {count} captured families after offset {start}; have {len(fresh)}")
        # Replay old data to retain C's already-good behaviors. No held-out rows.
        replay_path=dataset/"replay_captures.jsonl"
        if replay_path.exists():
            old_caps=read_jsonl(replay_path)
        chosen=fresh+old_caps[:min(len(old_caps),max(1,count//5))]
        validation=read_jsonl(dataset/"validation_captures.jsonl")
        vexamples=train.load_examples(validation,rng_seed=991)[:160]
    examples=train.load_examples(chosen)
    cfg=CONFIG["training"]["lora"]
    warmup=min(30,max(5,len(examples)//80))
    write_json(run_dir/"request.json",request)
    write_json(run_dir/"plan.json", {
        "name":name,"started":utc_now(),"control_old_data_only":control,"new_families":0 if control else count,
        "old_replay_families":len(chosen) if control else len(chosen)-count,"examples":len(examples),
        "source_family_ids":[c["family_id"] for c in chosen],"start_offset":start,
        "train_ids_sha256":sha256_text(json.dumps([c["family_id"] for c in chosen])),
        "dataset_dir":str(dataset),"dataset_freeze_sha256":file_sha256(dataset/"freeze.json") if not control else None,
        "validation_pair_ids":[e["pair_id"] for e in vexamples],"lr":lr,"warmup_updates":warmup,
        "initial_adapter":str(initial),"initial_adapter_sha256":file_sha256(initial/"adapters.safetensors"),
        "lora":cfg,"seed":20261013,"grad_accum":8,"max_sequence_tokens":6144,
        "method":"Same verified prefix-cached Gated DeltaNet training implementation; one epoch of selected families plus old-data replay.",
        "roles":dict(__import__('collections').Counter(e['role'] for e in examples))})
    model,tok=train.load_for_training(seed=20261013)
    model.load_weights(str(initial/"adapters.safetensors"),strict=False)
    # Verify that the source adapter actually loaded, avoiding accidental
    # training from a randomly initialized adapter under a continuation label.
    import mlx.core as mx
    from mlx.utils import tree_flatten
    expected=mx.load(str(initial/"adapters.safetensors"))
    actual=dict(tree_flatten(model.trainable_parameters()))
    if set(expected)!=set(actual):
        raise RuntimeError("Adapter parameter names do not match")
    if any(not mx.array_equal(v,actual[k]).item() for k,v in expected.items()):
        raise RuntimeError("Adapter restoration mismatch")
    del expected,actual
    blocks=train.make_blocks([{**train.split_example(tok,e),"pair_id":e["pair_id"],"family_id":e["family_id"]}
                              for e in examples],8,20261013)
    write_json(run_dir/"exposure-order.json",[[{"pair_id":it["pair_id"],"family_id":it["family_id"]}
                                              for it in block] for block in blocks])
    result=train.train_loop(model,tok,examples,vexamples,run_dir,lr=lr,warmup=warmup,
                  grad_accum=8,checkpoints=3,max_seq_length=6144,lora_cfg=cfg,log_every=10,
                  eval_every=max(40,len(examples)//80),seed=20261013)
    # Compare the actual saved checkpoints on the same response-token loss.
    # Logging intervals need not coincide with checkpoint boundaries.
    val_items=[train.split_example(tok,e) for e in vexamples]
    losses=[]
    model.eval()
    for checkpoint in sorted(run_dir.glob('ckpt-*')):
        model.load_weights(str(checkpoint/'adapters.safetensors'),strict=False)
        caches={};total=0.;tokens=0
        for item in val_items:
            if item['key'] not in caches:
                caches[item['key']]=train.prefix_cache(model,item['prefix'])
            loss,n=train.cached_response_loss(model,mx.array([item['suffix']]),
                       train.clone_cache(caches[item['key']]),item['off_s'])
            mx.eval(loss,n)
            total+=loss.item()*int(n.item());tokens+=int(n.item())
        losses.append({'checkpoint':checkpoint.name,'val_loss':total/max(tokens,1),'response_tokens':tokens})
        del caches
        mx.clear_cache()
    write_json(run_dir/'checkpoint-validation.json',{'created':utc_now(),'examples':len(vexamples),
               'checkpoints':losses,'lowest_loss':min(losses,key=lambda x:x['val_loss'])['checkpoint']})
    result.update(completed=utc_now(),adapter=str(run_dir/"final"))
    write_json(run_dir/"completion.json",result)
    return result


def export(name,checkpoint="final"):
    from lfx.export import candidate,content_digest
    adapter=ART/"train"/name/checkpoint
    if not (adapter/"adapters.safetensors").exists():
        raise FileNotFoundError(adapter)
    path=candidate(adapter,name+"-"+checkpoint)
    identity={"name":name,"checkpoint":checkpoint,"adapter":str(adapter),"quantized":str(path),
              "content_digest":content_digest(path),"adapter_sha256":file_sha256(adapter/"adapters.safetensors"),
              "size_bytes":sum(p.stat().st_size for p in path.iterdir() if p.is_file()),
              "quantization":"4-bit affine, group 64; same verified recipe as C","created":utc_now(),
              "installed":False}
    write_json(ART/"export"/(name+"-"+checkpoint+".identity.json"),identity)
    print(json.dumps(identity))
    return identity


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("stage",choices=["train","export"]);p.add_argument("name")
    p.add_argument("--count",type=int);p.add_argument("--start",type=int,default=0)
    p.add_argument("--control",action="store_true");p.add_argument("--initial-adapter");p.add_argument("--lr",type=float,default=3e-5)
    p.add_argument("--checkpoint",default="final");a=p.parse_args()
    if a.stage=="train":print(json.dumps(run(a.name,a.count,a.start,a.control,a.initial_adapter,a.lr)))
    else:export(a.name,a.checkpoint)
