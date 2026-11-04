import { vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useApi } from "../src/lib/useApi";
import { api, ErroApi } from "../src/lib/api";

const env = (dados: unknown) => ({ dados_ate: null, desatualizado: false, fontes: [], dados });
function adiada<T>() { let ok!: (v: T) => void, falha!: (e: unknown) => void; const p = new Promise<T>((a, b) => { ok = a; falha = b; }); return { p, ok, falha }; }
afterEach(() => { vi.restoreAllMocks(); });

test("trocar de url não mostra o dado da anterior e volta a carregar", async () => {
  const b = adiada<ReturnType<typeof env>>();
  vi.spyOn(api, "get").mockImplementation((u: string) => (u === "/a" ? Promise.resolve(env("A")) : b.p) as never);
  const { result, rerender } = renderHook(({ u }) => useApi<string>(u), { initialProps: { u: "/a" } });
  await waitFor(() => expect(result.current.env?.dados).toBe("A"));
  rerender({ u: "/b" });
  expect(result.current.estado).toBe("carregando");
  expect(result.current.env).toBeNull();
  await act(async () => { b.ok(env("B")); });
  await waitFor(() => expect(result.current.env?.dados).toBe("B"));
  expect(result.current.estado).toBe("ok");
});

test("erro ao recarregar a mesma url mantém o último dado bom", async () => {
  let falha = false;
  vi.spyOn(api, "get").mockImplementation((() => (falha ? Promise.reject(new ErroApi(500, "x", "quebrou")) : Promise.resolve(env("B")))) as never);
  const { result } = renderHook(() => useApi<string>("/b"));
  await waitFor(() => expect(result.current.env?.dados).toBe("B"));
  falha = true;
  let pr!: Promise<void>;
  act(() => { pr = result.current.recarregar(); });
  await act(async () => { await pr; });
  expect(result.current.estado).toBe("erro");
  expect(result.current.env?.dados).toBe("B");
});

test("recarregar só resolve depois da resposta da url atual", async () => {
  const a = adiada<ReturnType<typeof env>>();
  vi.spyOn(api, "get").mockImplementation((u: string) => (u === "/a" ? a.p : Promise.resolve(env("B"))) as never);
  const { result, rerender } = renderHook(({ u }) => useApi<string>(u), { initialProps: { u: "/a" } });
  rerender({ u: "/b" });
  await waitFor(() => expect(result.current.env?.dados).toBe("B"));
  const b2 = adiada<ReturnType<typeof env>>();
  vi.spyOn(api, "get").mockImplementation((u: string) => (u === "/a" ? a.p : b2.p) as never);
  let resolvido = false;
  let pr!: Promise<void>;
  act(() => { pr = result.current.recarregar().then(() => { resolvido = true; }); });
  await act(async () => { a.ok(env("A")); });
  expect(resolvido).toBe(false);
  await act(async () => { b2.ok(env("B2")); await pr; });
  expect(resolvido).toBe(true);
  expect(result.current.env?.dados).toBe("B2");
});
