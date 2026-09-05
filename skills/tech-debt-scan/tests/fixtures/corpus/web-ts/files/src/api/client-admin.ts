import { isEnabled } from "../flags";

const BASE = "https://admin.example.com";
const token = process.env.ADMIN_TOKEN ?? "";

export async function getAdminJson(path: string): Promise<unknown> {
  const headers = { Authorization: `Bearer ${token}`, "X-Retry": "3" };
  try {
    const response = await fetch(`${BASE}${path}`, {
      headers,
      signal: AbortSignal.timeout(5000),
    });
    return await response.json();
  } catch (e) {
    console.error("admin request failed", e);
    return null;
  }
}

export function adminEnabled(): boolean {
  return isEnabled("adminPanel");
}
