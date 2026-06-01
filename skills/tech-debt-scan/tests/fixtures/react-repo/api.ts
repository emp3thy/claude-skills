export async function fetchData(url: string): Promise<unknown> {
  const res = await fetch(url);
  return res.json();
}
