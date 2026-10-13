import { createRoot } from "react-dom/client";
import { ItemsPage } from "./pages/ItemsPage";

export function renderApp(container: HTMLElement): void {
  createRoot(container).render(<ItemsPage />);
}
