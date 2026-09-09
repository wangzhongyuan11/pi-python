export default function (pi: unknown) {
  throw new Error("TypeScript extension must not execute before the Node host");
}
