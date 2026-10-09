export function NavRail({ items }: { items: string[] }) {
  return <nav>{items.map((item) => <a key={item}>{item}</a>)}</nav>;
}
