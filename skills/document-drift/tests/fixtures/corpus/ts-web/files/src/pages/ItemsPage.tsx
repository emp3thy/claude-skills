import { useEffect, useState } from "react";
import { listItems, type Item } from "../api/client";
import { formatPrice } from "../helpers/format";

export function ItemsPage() {
  const [items, setItems] = useState<Item[]>([]);
  useEffect(() => {
    listItems().then(setItems);
  }, []);
  return (
    <ul>
      {items.map((item) => (
        <li key={item.id}>
          {item.name}: {formatPrice(item.priceCents)}
        </li>
      ))}
    </ul>
  );
}
