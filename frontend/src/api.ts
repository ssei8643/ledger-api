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

// POSTでJSONを送る。サーバーに接続できないときは例外になるので、呼び出し側で catch する
export function postJson(path: string, body: unknown): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
}

// エラーのレスポンスから、画面に出すメッセージを取り出す
export async function detailText(res: Response): Promise<string> {
  try {
    const body = await res.json()
    const detail = body.detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail)) {
      // Pydanticは、バリデーターで投げたエラーの先頭に "Value error, " を付けるので取り除く
      return detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, "")).join(" / ")
    }
  } catch {
    // JSONではない応答（起動中のサーバーが返すHTMLなど）は、下の文言にする
  }
  return `サーバーがエラーを返しました（HTTP ${res.status}）`
}
