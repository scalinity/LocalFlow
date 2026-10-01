<script lang="ts" module>
  // One icon family (Lucide outline, ISC) at one stroke weight. Pages ask
  // for icons by name so a single table decides the whole app's glyphs.
  import LayoutGrid from '@lucide/svelte/icons/layout-grid';
  import ListClock from '@lucide/svelte/icons/list-clock';
  import ChartColumn from '@lucide/svelte/icons/chart-column';
  import BookA from '@lucide/svelte/icons/book-a';
  import Scissors from '@lucide/svelte/icons/scissors';
  import Type from '@lucide/svelte/icons/type';
  import WandSparkles from '@lucide/svelte/icons/wand-sparkles';
  import NotebookPen from '@lucide/svelte/icons/notebook-pen';
  import Cpu from '@lucide/svelte/icons/cpu';
  import Activity from '@lucide/svelte/icons/activity';
  import Settings from '@lucide/svelte/icons/settings';
  import Search from '@lucide/svelte/icons/search';
  import ArrowUpDown from '@lucide/svelte/icons/arrow-up-down';
  import RefreshCw from '@lucide/svelte/icons/refresh-cw';
  import Copy from '@lucide/svelte/icons/copy';
  import ClipboardPaste from '@lucide/svelte/icons/clipboard-paste';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import EllipsisVertical from '@lucide/svelte/icons/ellipsis-vertical';
  import Pencil from '@lucide/svelte/icons/pencil';
  import Trash from '@lucide/svelte/icons/trash';
  import Star from '@lucide/svelte/icons/star';
  import Pin from '@lucide/svelte/icons/pin';
  import X from '@lucide/svelte/icons/x';
  import Plus from '@lucide/svelte/icons/plus';
  import ArrowRight from '@lucide/svelte/icons/arrow-right';
  import Info from '@lucide/svelte/icons/info';
  import Check from '@lucide/svelte/icons/check';
  import RotateCcw from '@lucide/svelte/icons/rotate-ccw';
  import Play from '@lucide/svelte/icons/play';
  import Square from '@lucide/svelte/icons/square';
  import Mic from '@lucide/svelte/icons/mic';
  import Keyboard from '@lucide/svelte/icons/keyboard';
  import Monitor from '@lucide/svelte/icons/monitor';
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import Sun from '@lucide/svelte/icons/sun';
  import Moon from '@lucide/svelte/icons/moon';
  import Laptop from '@lucide/svelte/icons/laptop';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import Globe from '@lucide/svelte/icons/globe';
  import AudioLines from '@lucide/svelte/icons/audio-lines';
  import FileText from '@lucide/svelte/icons/file-text';
  import Download from '@lucide/svelte/icons/download';
  import Upload from '@lucide/svelte/icons/upload';
  import MessageSquare from '@lucide/svelte/icons/message-square';
  import Mail from '@lucide/svelte/icons/mail';
  import CodeXml from '@lucide/svelte/icons/code-xml';
  import Terminal from '@lucide/svelte/icons/terminal';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import CircleAlert from '@lucide/svelte/icons/circle-alert';
  import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark';
  import ThumbsUp from '@lucide/svelte/icons/thumbs-up';
  import ThumbsDown from '@lucide/svelte/icons/thumbs-down';
  import Undo2 from '@lucide/svelte/icons/undo-2';
  import Split from '@lucide/svelte/icons/split';
  import Scale from '@lucide/svelte/icons/scale';
  import Clock from '@lucide/svelte/icons/clock';
  import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
  import Database from '@lucide/svelte/icons/database';
  import Power from '@lucide/svelte/icons/power';
  import BookOpenText from '@lucide/svelte/icons/book-open-text';
  import Funnel from '@lucide/svelte/icons/funnel';
  import EyeOff from '@lucide/svelte/icons/eye-off';
  import Eye from '@lucide/svelte/icons/eye';
  import FolderOpen from '@lucide/svelte/icons/folder-open';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import Hash from '@lucide/svelte/icons/hash';
  import Languages from '@lucide/svelte/icons/languages';
  import Paperclip from '@lucide/svelte/icons/paperclip';

  export const ICONS = {
    home: LayoutGrid,
    history: ListClock,
    insights: ChartColumn,
    dictionary: BookA,
    snippets: Scissors,
    styles: Type,
    transforms: WandSparkles,
    scratchpad: NotebookPen,
    models: Cpu,
    diagnostics: Activity,
    settings: Settings,
    search: Search,
    sort: ArrowUpDown,
    refresh: RefreshCw,
    copy: Copy,
    paste: ClipboardPaste,
    more: Ellipsis,
    'more-vertical': EllipsisVertical,
    edit: Pencil,
    trash: Trash,
    star: Star,
    pin: Pin,
    close: X,
    plus: Plus,
    arrow: ArrowRight,
    info: Info,
    check: Check,
    retry: RotateCcw,
    play: Play,
    stop: Square,
    mic: Mic,
    keyboard: Keyboard,
    monitor: Monitor,
    privacy: ShieldCheck,
    sun: Sun,
    moon: Moon,
    system: Laptop,
    sparkles: Sparkles,
    globe: Globe,
    audio: AudioLines,
    file: FileText,
    download: Download,
    upload: Upload,
    message: MessageSquare,
    mail: Mail,
    code: CodeXml,
    terminal: Terminal,
    'chevron-down': ChevronDown,
    'chevron-right': ChevronRight,
    'chevron-left': ChevronLeft,
    alert: CircleAlert,
    help: CircleQuestionMark,
    'thumbs-up': ThumbsUp,
    'thumbs-down': ThumbsDown,
    undo: Undo2,
    split: Split,
    scale: Scale,
    clock: Clock,
    sliders: SlidersHorizontal,
    database: Database,
    power: Power,
    book: BookOpenText,
    filter: Funnel,
    'eye-off': EyeOff,
    eye: Eye,
    folder: FolderOpen,
    compose: SquarePen,
    hash: Hash,
    languages: Languages,
    attach: Paperclip,
  } as const;

  export type IconName = keyof typeof ICONS;
</script>

<script lang="ts">
  let {
    name,
    size = 17,
    stroke = 1.6,
    label = undefined,
  }: { name: IconName; size?: number; stroke?: number; label?: string } = $props();
  const Glyph = $derived(ICONS[name]);
</script>

<Glyph
  {size}
  strokeWidth={stroke}
  absoluteStrokeWidth
  aria-hidden={label ? undefined : 'true'}
  aria-label={label}
  role={label ? 'img' : undefined}
/>
