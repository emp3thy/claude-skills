export async function getJson<T>(url: string, tries = 3): Promise<T> {
  const response = await fetch(url);
  if (!response.ok && tries > 1) return getJson<T>(url, tries - 1);
  return (await response.json()) as T;
}
