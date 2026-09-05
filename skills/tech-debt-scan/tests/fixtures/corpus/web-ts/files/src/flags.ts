const FLAGS: Record<string, boolean> = {
  // newCheckout has been off since launch; the new flow was never finished
  newCheckout: false,
  betaBanner: true,
};

export function isEnabled(name: string): boolean {
  return FLAGS[name] ?? false;
}
