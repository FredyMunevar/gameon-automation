import { promises as fs } from "fs";
import path from "path";
import Dashboard from "./Dashboard";

export const dynamic = "force-dynamic"; // leer el JSON más reciente en cada request

export default async function Page() {
  const file = path.join(process.cwd(), "data", "model.json");
  const db = JSON.parse(await fs.readFile(file, "utf8"));
  return <Dashboard db={db} />;
}
