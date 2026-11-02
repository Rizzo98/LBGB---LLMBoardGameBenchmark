import { mount } from "svelte";
import App from "./App.svelte";

const target = document.getElementById("app");
if (target === null) {
  throw new Error("the console shell needs an #app element");
}

mount(App, { target });
