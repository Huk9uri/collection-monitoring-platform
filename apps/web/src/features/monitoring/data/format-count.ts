export function formatCount(value: number | null): string {
  return value === null ? '-' : value.toLocaleString('ko-KR')
}
