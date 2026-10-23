export interface SelectOption { value: string; label: string; badge?: string; disabled?: boolean }
export function nextEnabled(options: SelectOption[], from: number, direction: number): number {
  for (let step = 1; step <= options.length; step++) {
    const i = ((from + step * direction) % options.length + options.length) % options.length;
    if (!options[i].disabled) return i;
  }
  return -1;
}
export function matchingOption(options: SelectOption[], query: string, from: number): number {
  const lower = query.toLocaleLowerCase();
  const prefix = [...lower].every((c) => c === lower[0]) ? lower[0] : lower;
  for (let step = 1; step <= options.length; step++) {
    const i = (Math.max(from, -1) + step) % options.length;
    if (!options[i].disabled && options[i].label.toLocaleLowerCase().startsWith(prefix)) return i;
  }
  return -1;
}
