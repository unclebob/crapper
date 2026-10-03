import { view } from "./view";

export function check(): boolean {
  return view(true) === 1;
}
