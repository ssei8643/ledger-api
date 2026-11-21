import { useEffect, useState, type ChangeEvent } from "react"

type Account = {
  name: string
  category: string
}

type BankDraft = {
  import_key: string
  entry_date: string
  description: string
  direction: "in" | "out"
  amount: number
  account: string | null
  already_imported: boolean
}

type Props = {
  onImported: () => void
}

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000"

// 銀行のCSVはShift_JISのことが多いので、UTF-8で読めなければShift_JISで読み直す
function decodeCsv(buffer: ArrayBuffer): string {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(buffer)
  } catch {
    return new TextDecoder("shift_jis").decode(buffer)
  }
}

async function errorText(res: Response): Promise<string> {
  const body = await res.json()
  const detail = body.detail
  return typeof detail === "string"
    ? detail
    : detail.map((d: { msg: string }) => d.msg).join(" / ")
}

export default function BankImport({ onImported }: Props) {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [drafts, setDrafts] = useState<BankDraft[]>([])
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_URL}/accounts`)
      .then((res) => res.json())
      .then((json: Account[]) => setAccounts(json))
  }, [])

  async function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const input = e.target
    const file = input.files?.[0]
    if (!file) return
    setMessage(null)

    const csvText = decodeCsv(await file.arrayBuffer())
    const res = await fetch(`${API_URL}/bank-import/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csv_text: csvText }),
    })
    if (res.ok) {
      setDrafts(await res.json())
    } else {
      setDrafts([])
      setMessage(`読み込めませんでした：${await errorText(res)}`)
    }
    input.value = "" // 同じファイルをもう一度選べるようにする
  }

  function updateAccount(index: number, account: string) {
    setDrafts(drafts.map((d, i) => (i === index ? { ...d, account: account || null } : d)))
  }

  const targets = drafts.filter((d) => !d.already_imported)
  const allSelected = targets.length > 0 && targets.every((d) => d.account)

  async function handleImport() {
    const res = await fetch(`${API_URL}/bank-import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ drafts: targets }),
    })
    if (res.ok) {
      setMessage(`${targets.length}件の仕訳を登録しました`)
      setDrafts([])
      onImported()
    } else {
      setMessage(`登録できませんでした：${await errorText(res)}`)
    }
  }

  return (
    <div>
      <h2>銀行明細の取り込み</h2>
      <p>
        「日付,摘要,出金,入金」の形式のCSVを選んでください。
        <a href="/sample-bank.csv" download>サンプルCSVをダウンロード</a>
      </p>
      <input type="file" accept=".csv" onChange={handleFile} />

      {drafts.length > 0 && (
        <>
          <table>
            <thead>
              <tr>
                <th>日付</th>
                <th>摘要</th>
                <th>出金</th>
                <th>入金</th>
                <th>勘定科目</th>
              </tr>
            </thead>
            <tbody>
              {drafts.map((d, i) => (
                <tr key={d.import_key}>
                  <td>{d.entry_date}</td>
                  <td>{d.description}</td>
                  <td>{d.direction === "out" ? d.amount.toLocaleString() : ""}</td>
                  <td>{d.direction === "in" ? d.amount.toLocaleString() : ""}</td>
                  <td>
                    {d.already_imported ? (
                      "取り込み済み"
                    ) : (
                      <select
                        value={d.account ?? ""}
                        onChange={(e) => updateAccount(i, e.target.value)}
                      >
                        <option value="">選択してください</option>
                        {accounts.map((a) => (
                          <option key={a.name} value={a.name}>
                            {a.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button onClick={handleImport} disabled={!allSelected}>
            {targets.length}件を仕訳として登録
          </button>
        </>
      )}

      {message && <p>{message}</p>}
    </div>
  )
}