import { config } from "../config";

export const PAGE_SIZE = 50;

export interface Item {
  id: string;
  name: string;
  priceCents: number;
}

export async function listItems(page = 1): Promise<Item[]> {
  const url = `${config.apiUrl}/api/items?page=${page}&size=${PAGE_SIZE}`;
  const response = await fetch(url);
  return (await response.json()) as Item[];
}

export async function fetchItem(id: string): Promise<Item> {
  const response = await fetch(`${config.apiUrl}/api/items/${id}`);
  return (await response.json()) as Item;
}
