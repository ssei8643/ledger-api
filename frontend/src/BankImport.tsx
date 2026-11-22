import { useEffect, useState, type ChangeEvent } from "react"
import { detailText, errorMessage, getJson, postJson } from "./api"

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

// 銀行口座の科目。相手科目に選ぶと借方と貸方が同じ科目になるので、選択肢から外す
const BANK_ACCOUNT = "普通預金"

// 銀行のCSVはShift_JISのことが多いので、UTF-8で読めなければShift_JISで読み直す
function decodeCsv(buffer: ArrayBuffer): string {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(buffer)
  } catch {
    return new TextDecoder("shift_jis").decode(buffer)
  }
}

export default function BankImport({ onImported }: Props) {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [drafts, setDrafts] = useState<BankDraft[]>([])
  const [message, setMessage] = useState<string | null>(null)
  // 送信中はボタンを押せないようにする
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    getJson<Account[]>("/accounts")
      .then((json) => setAccounts(json.filter((a) => a.name !== BANK_ACCOUNT)))
      .catch((e) => setMessage(`勘定科目を読み込めませんでした：${errorMessage(e)}`))
  }, [])

  async function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const input = e.target
    const file = input.files?.[0]
    if (!file) return
    setMessage(null)

    try {
      const csvText = decodeCsv(await file.arrayBuffer())
      const res = await postJson("/bank-import/preview", { csv_text: csvText })
      if (res.ok) {
        setDrafts(await res.json())
      } else {
        setDrafts([])
        setMessage(`読み込めませんでした：${await detailText(res)}`)
      }
    } catch (e) {
      setDrafts([])
      setMessage(`読み込めませんでした：${errorMessage(e)}`)
    } finally {
      input.value = "" // 同じファイルをもう一度選べるようにする
    }
  }

  function updateAccount(index: number, account: string) {
    setDrafts(drafts.map((d, i) => (i === index ? { ...d, account: account || null } : d)))
  }

  const targets = drafts.filter((d) => !d.already_imported)
  const allSelected = targets.length > 0 && targets.every((d) => d.account)

  async function handleImport() {
    setSubmitting(true)
    try {
      const res = await postJson("/bank-import", { drafts: targets })
      if (res.ok) {
        setMessage(`${targets.length}件の仕訳を登録しました`)
        setDrafts([])
        onImported()
      } else {
        setMessage(`登録できませんでした：${await detailText(res)}`)
      }
    } catch (e) {
      setMessage(`登録できませんでした：${errorMessage(e)}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <h2>銀行明細の取り込み</h2>
      <p>
        銀行の入出金明細のCSVを選んでください（日付・摘要・金額の列が必要です）。
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
          <button onClick={handleImport} disabled={!allSelected || submitting}>
            {submitting ? "送信中..." : `${targets.length}件を仕訳として登録`}
          </button>
        </>
      )}

      {message && <p>{message}</p>}
    </div>
  )
}