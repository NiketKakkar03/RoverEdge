import "./style.css";
import { mountApp } from "./app";

const root = document.querySelector<HTMLElement>("#app");
if (!root) throw new Error("RoverEdge application root is missing");
void mountApp(root);
