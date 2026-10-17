"""Continue the preserved adapter using the verified prefix-cached MLX loop."""
from __future__ import annotations

import argparse
import collections
import json
import random
from pathlib import Path
from .common import *


def prompt_prefixes(captures):
    """Per role, the hashed system and few-shot prefix keys lfx.train caches."""
    from lfx.train import USER_TURN
    out = collections.defaultdict(set)
    for cap in captures:
        for call in cap["calls"]:
            out[call["role"]].add(sha256_text(call["prompt"][:call["prompt"].rfind(USER_TURN)]))
    return out


def checked_dataset(dataset, *, require_current_capture_source=True):
    freeze = read_json(dataset / "freeze.json")
    if not freeze:
        raise RuntimeError("Evaluation sets must be fixed first")
    if any(file_sha256(dataset / (name + ".jsonl" if name in ("test", "validation") else name)) != digest
           for name, digest in freeze.get("files", {}).items()):
        raise RuntimeError("Frozen dataset file changed")
    capture_hashes = freeze.get("capture_source_hashes", {})
    if require_current_capture_source and any(
            file_sha256(ROOT / path) != digest for path, digest in capture_hashes.items()):
        raise RuntimeError("Training prompt source changed after capture")
    # Validation loss selects checkpoints, so it must score the prompts training serves.
    if freeze.get("validation_capture_source_hashes", capture_hashes) != capture_hashes:
        raise RuntimeError("Validation captures were made from different prompt sources than training captures")
    paths = [dataset / (split + "_captures.jsonl") for split in ("validation", "train")]
    if all(path.exists() for path in paths):
        validation, train = (prompt_prefixes(read_jsonl(path)) for path in paths)
        if any(validation[role] != train[role] for role in validation.keys() & train.keys()):
            raise RuntimeError("Validation captures use different prompts from training captures")
    return freeze


def run(name, count, start=0, control=False, initial_adapter=None, lr=3e-5, dataset_dir=None, checkpoints=3,
        log_every=10, base=None):
    from lfx import train
    seed = train.training_seed(20261013)
    run_dir=ART/"train"/name
    dataset=Path(dataset_dir) if dataset_dir else ART/"dataset"
    # Another base model starts from a fresh adapter: C's adapter only fits Qwen3.5-4B.
    initial=Path(initial_adapter) if initial_adapter else None if base else Path(c_identity()["adapter_path"])
    freeze = None if control else checked_dataset(dataset)
    request = {"name":name,"count":count,"start":start,"control":control,"lr":lr,
               "dataset_dir":str(dataset.resolve()),
               "dataset_freeze_sha256":file_sha256(dataset/"freeze.json") if not control else None,
               "initial_adapter":str(initial.resolve()) if initial else None,
               "initial_adapter_sha256":file_sha256(initial/"adapters.safetensors") if initial else None,
               "training_config":CONFIG["training"]}
    if base:
        request["base"] = str(Path(base).resolve())
    if train.LFX_SEED:
        request["lfx_seed"] = train.LFX_SEED
    if checkpoints != 3:
        # Recorded only when it differs, so earlier completed runs keep their identity.
        request["checkpoints"] = checkpoints
    if log_every != 10:
        request["log_every"] = log_every
    if (run_dir/"completion.json").exists():
        if read_json(run_dir/"request.json") != request:
            raise RuntimeError("Completed training name belongs to another or unrecorded request")
        return read_json(run_dir/"completion.json")
    if (run_dir/"metrics.jsonl").exists():
        raise RuntimeError("Interrupted run retained; use a distinct run name with an explicit initial adapter")
    replay,replay_origin=[],None
    if control:
        old_pairs=read_jsonl(OLD_ART/"dataset/train.jsonl")
        verified={p["pair_id"] for p in old_pairs if p.get("verification")=="PASS"}
        old_caps=[p for p in read_jsonl(OLD_ART/"dataset/train_captures.jsonl") if p["pair_id"] in verified]
        random.Random(seed).shuffle(old_caps)
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
        # Replay retains C's already-good behaviors. First-experiment captures
        # were rendered with older prompts, so the dataset must supply its own.
        replay_path=dataset/"replay_captures.jsonl"
        if not replay_path.exists():
            raise RuntimeError("Dataset has no replay_captures.jsonl; first-experiment captures use older prompts")
        replay=read_jsonl(replay_path)[:max(1,count//5)]
        replay_origin=freeze.get("stats",{}).get("replay",{}).get("source")
        if replay and not replay_origin:
            raise RuntimeError("Dataset freeze does not state the replay origin (stats.replay.source)")
        chosen=fresh+replay
        validation=read_jsonl(dataset/"validation_captures.jsonl")
        vexamples=train.load_examples(validation,rng_seed=991)[:160]
    examples=train.load_examples(chosen)
    cfg=CONFIG["training"]["lora"]
    warmup=min(30,max(5,len(examples)//80))
    write_json(run_dir/"request.json",request)
    write_json(run_dir/"plan.json", {
        "name":name,"started":utc_now(),"control_old_data_only":control,"new_families":0 if control else count,
        "replay":{"origin":replay_origin,"presentations":len(replay),
                  "unique_pair_ids":sorted({c["pair_id"] for c in replay})},"examples":len(examples),
        "source_family_ids":[c["family_id"] for c in chosen],"chosen_pair_ids":[c["pair_id"] for c in chosen],
        "start_offset":start,
        "train_ids_sha256":sha256_text(json.dumps([c["family_id"] for c in chosen])),
        "dataset_dir":str(dataset),"dataset_freeze_sha256":file_sha256(dataset/"freeze.json") if not control else None,
        "validation_pair_ids":[e["pair_id"] for e in vexamples],"lr":lr,"warmup_updates":warmup,
        "initial_adapter":str(initial) if initial else None,
        "initial_adapter_sha256":file_sha256(initial/"adapters.safetensors") if initial else None,
        **({"base":request["base"]} if base else {}),
        "lora":cfg,"seed":seed,"grad_accum":8,"max_sequence_tokens":6144,
        "method":"Same verified prefix-cached Gated DeltaNet training implementation; one epoch of the selected captures.",
        "roles":dict(__import__('collections').Counter(e['role'] for e in examples))})
    model,tok=train.load_for_training(seed=seed,base=request.get("base"))
    import mlx.core as mx
    if initial:
        model.load_weights(str(initial/"adapters.safetensors"),strict=False)
        # Verify that the source adapter actually loaded, avoiding accidental
        # training from a randomly initialized adapter under a continuation label.
        from mlx.utils import tree_flatten
        expected=mx.load(str(initial/"adapters.safetensors"))
        actual=dict(tree_flatten(model.trainable_parameters()))
        if set(expected)!=set(actual):
            raise RuntimeError("Adapter parameter names do not match")
        if any(not mx.array_equal(v,actual[k]).item() for k,v in expected.items()):
            raise RuntimeError("Adapter restoration mismatch")
        del expected,actual
    # The loop trains these exact blocks, so the recorded order is the trained one.
    blocks=train.make_blocks([{**train.split_example(tok,e),"pair_id":e["pair_id"],"family_id":e["family_id"]}
                              for e in examples],8,seed)
    result=train.train_loop(model,tok,examples,vexamples,run_dir,lr=lr,warmup=warmup,
                  grad_accum=8,checkpoints=checkpoints,max_seq_length=6144,lora_cfg=cfg,log_every=log_every,
                  eval_every=max(40,len(examples)//80),seed=seed,blocks=blocks,base=request.get("base"))
    exposure=[[{"pair_id":it["pair_id"],"family_id":it["family_id"]} for it in block]
              for block in blocks[:result["updates"]]]
    write_json(run_dir/"exposure-order.json",exposure)
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
    trained_prefixes={it['key'] for block in blocks for it in block}
    write_json(run_dir/'checkpoint-validation.json',{'created':utc_now(),'examples':len(vexamples),
               'prompt_matches_training':{it['key'] for it in val_items}<=trained_prefixes,
               'checkpoints':losses,'lowest_loss':min(losses,key=lambda x:x['val_loss'])['checkpoint']})
    result.update(completed=utc_now(),adapter=str(run_dir/"final"),
                  chosen_pair_ids=[c["pair_id"] for c in chosen],exposure_order=exposure)
    write_json(run_dir/"completion.json",result)
    return result


def export(name,checkpoint="final",*,compact_metadata=False,bf16_base=None):
    from lfx.export import candidate,content_digest
    adapter=ART/"train"/name/checkpoint
    if not (adapter/"adapters.safetensors").exists():
        raise FileNotFoundError(adapter)
    export_name=name+"-"+checkpoint+("-compact" if compact_metadata else "")
    adapter_sha256=file_sha256(adapter/"adapters.safetensors")
    # candidate() reuses an existing quantized directory, so it must be this adapter's.
    prior=read_json(ART/"export"/(export_name+".identity.json"))
    if prior and prior.get("adapter_sha256")!=adapter_sha256:
        raise RuntimeError("Export name already holds another adapter's quantized weights")
    if not prior and (ART/"export"/"candidates"/export_name).exists():
        raise RuntimeError("Quantized candidate exists without an identity record")
    base=(read_json(ART/"train"/name/"request.json") or {}).get("base")
    # An adapter trained on a GPU pod recorded the pod's base path; bf16_base names the local bf16 base instead.
    path=candidate(adapter,export_name,base=base,**({} if bf16_base is None else {"bf16_base":bf16_base}))
    metadata_receipt=None
    if compact_metadata:
        from .export_metadata import compact_json_metadata
        metadata_receipt=compact_json_metadata(path)
    identity={"name":name,"checkpoint":checkpoint,"adapter":str(adapter),"quantized":str(path),
              "content_digest":content_digest(path),"adapter_sha256":adapter_sha256,
              "size_bytes":sum(p.stat().st_size for p in path.iterdir() if p.is_file()),
              "quantization":"4-bit affine, group 64; same verified recipe as C","created":utc_now(),
              "installed":False}
    if bf16_base is not None:
        identity.update(bf16_base=str(bf16_base),request_base=base,
                        quantization="4-bit affine, group 64; LoRA fused into the bf16 base and quantized, same recipe as C")
    elif base:
        identity.update(base=base,quantization="4-bit affine, group 64; LoRA fused into the 4-bit base and requantized")
    if metadata_receipt is not None:
        identity["metadata_compaction"]=metadata_receipt
    write_json(ART/"export"/(export_name+".identity.json"),identity)
    print(json.dumps(identity))
    return identity


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("stage",choices=["train","export"]);p.add_argument("name")
    p.add_argument("--count",type=int);p.add_argument("--start",type=int,default=0)
    p.add_argument("--control",action="store_true");p.add_argument("--initial-adapter");p.add_argument("--lr",type=float,default=3e-5)
    p.add_argument("--checkpoint",default="final")
    p.add_argument("--bf16-base",help='local bf16 base for an adapter trained on a GPU pod: "4b" or a model directory')
    p.add_argument("--compact",action="store_true",help="also compact the quantized candidate's JSON metadata")
    a=p.parse_args()
    if a.stage=="train":print(json.dumps(run(a.name,a.count,a.start,a.control,a.initial_adapter,a.lr)))
    else:export(a.name,a.checkpoint,compact_metadata=a.compact,bf16_base=a.bf16_base)
