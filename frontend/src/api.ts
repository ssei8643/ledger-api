export const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000"

// GETでデータを取得する。サーバーがエラーを返したときも、
// 通信そのものに失敗したときも例外にして、呼び出し側でメッセージを出せるようにする
export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`)
  if (!res.ok) {
    throw new Error(`サーバーがエラーを返しました（HTTP ${res.status}）`)
  }
  return (await res.json()) as T
}

// 画面に表示するエラーメッセージを作る
export function errorMessage(e: unknown): string {
  // fetch は、サーバーに接続できないときに TypeError を投げる
  if (e instanceof TypeError) {
    return "サーバーに接続できませんでした。起動に1分ほどかかることがあるので、少し待ってから再読み込みしてください"
  }
  return e instanceof Error ? e.message : String(e)
}
