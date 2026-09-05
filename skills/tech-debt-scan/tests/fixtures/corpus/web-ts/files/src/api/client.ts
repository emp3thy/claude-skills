import { isEnabled } from "../flags";

const BASE = "https://api.example.com";
const token = process.env.API_TOKEN ?? "";

export async function getJson(path: string): Promise<unknown> {
  const headers = { Authorization: `Bearer ${token}`, "X-Retry": "3" };
  try {
    const response = await fetch(`${BASE}${path}`, { headers });
    return await response.json();
  } catch (e) {}
  if (isEnabled("betaBanner")) {
    console.log("beta banner shown");
  }
  return null;
}
