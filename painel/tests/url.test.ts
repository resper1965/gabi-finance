import { urlSegura } from "../src/lib/url";

test("urlSegura deixa passar só http(s)", () => {
  expect(urlSegura("https://x")).toBe("https://x");
  expect(urlSegura("http://x/y")).toBe("http://x/y");
  for (const ruim of ["javascript:alert(1)", "data:text/html,x", "lixo", "", null, undefined]) expect(urlSegura(ruim)).toBeNull();
});
