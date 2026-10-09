export function readToken(): string | null {
  return sessionStorage.getItem("token");
}
