import express from "express";
import { config } from "./config";

const app = express();

app.get("/api/items", (req, res) => {
  res.json([]);
});

app.get("/api/items/:id", (req, res) => {
  res.json({ id: req.params.id });
});

export function start(): void {
  app.listen(config.port);
}
