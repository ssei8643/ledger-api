import { useEffect, useState, type FormEvent } from "react"
import { detailText, errorMessage, getJson, postJson } from "./api"

type Side = "debit" | "credit"

type LineInput = {
  account: string
  side: Side
  amount: number
}

type Props = {
  onCreated: () => void
}

type Account = {
  name: string
  category: string
}

type JournalTemplate = {
  name: string
  description: string
  lines: { account: string; side: Side }[]
}

function emptyLine(side: Side): LineInput {
  return { account: "", side, amount: 0 }
}

// 今日の日付（YYYY-MM-DD）。toISOString() はUTCなので、日本時間の0時〜9時は前日になってしまう
function today(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export default function JournalForm({ onCreated }: Props) {
  const [entryDate, setEntryDate] = useState(today())
  const [description, setDescription] = useState("")
  const [lines, setLines] = useState<LineInput[]>([emptyLine("debit"), emptyLine("credit")])
  const [message, setMessage] = useState<string | null>(null)
  // 送信中は登録ボタンを押せないようにする（サーバーの起動待ちで二重登録しないため）
  const [submitting, setSubmitting] = useState(false)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  // 画面を開いたときに、バックエンドから勘定科目の一覧を取得
  useEffect(() => {
    getJson<Account[]>("/accounts")
      .then((json) => setAccounts(json))
      .catch((e) => setLoadError(`勘定科目を読み込めませんでした：${errorMessage(e)}`))
  }, [])

  const [templates, setTemplates] = useState<JournalTemplate[]>([])

  // 画面を開いたときに、テンプレートの一覧を取得
  useEffect(() => {
    getJson<JournalTemplate[]>("/templates")
      .then((json) => setTemplates(json))
      .catch((e) => setLoadError(`テンプレートを読み込めませんでした：${errorMessage(e)}`))
  }, [])

  // テンプレートを選ぶと、摘要と科目・借貸を自動で入力
  function applyTemplate(name: string) {
    const t = templates.find((t) => t.name === name)
    if (!t) return
    setDescription(t.description)
    setLines(t.lines.map((l) => ({ ...l, amount: 0 })))
  }

  // 借方1行・貸方1行の仕訳は必ず同額になるので、両方に反映する
  function updateAmount(index: number, amount: number) {
    const isSimple = lines.length === 2 && lines[0].side !== lines[1].side
    if (isSimple) {
      setLines(lines.map((l) => ({ ...l, amount })))
    } else {
      updateLine(index, { amount })
    }
  }

  // 入力中の借方・貸方の合計（画面上でリアルタイムに計算）
  const debitTotal = lines.filter((l) => l.side === "debit").reduce((sum, l) => sum + l.amount, 0)
  const creditTotal = lines.filter((l) => l.side === "credit").reduce((sum, l) => sum + l.amount, 0)
  const isBalanced = debitTotal > 0 && debitTotal === creditTotal
  const allSelected = lines.every((l) => l.account !== "")
  // 同じ科目を借方と貸方の両方に使うことはできない（サーバーでも拒否される）
  const debitAccounts = lines.filter((l) => l.side === "debit").map((l) => l.account)
  const hasSameAccount = lines.some(
      (l) => l.side === "credit" && l.account !== "" && debitAccounts.includes(l.account),
  )

  function updateLine(index: number, changes: Partial<LineInput>) {
    setLines(lines.map((l, i) => (i === index ? { ...l, ...changes } : l)))
  }

  function addLine() {
    setLines([...lines, emptyLine("debit")])
  }

  function removeLine(index: number) {
    setLines(lines.filter((_, i) => i !== index))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setMessage(null)
    setSubmitting(true)

    try {
      const res = await postJson("/journal-entries", {
        entry_date: entryDate,
        description,
        lines,
      })
      if (res.ok) {
        setMessage("登録しました")
        setDescription("")
        setLines([emptyLine("debit"), emptyLine("credit")])
        onCreated()
      } else {
        setMessage(`登録できませんでした：${await detailText(res)}`)
      }
    } catch (e) {
      // サーバーに接続できなかったとき（休眠中など）
      setMessage(`登録できませんでした：${errorMessage(e)}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <h2>仕訳の入力</h2>
      {loadError && <p>{loadError}</p>}
      <div>
        <select value="" onChange={(e) => applyTemplate(e.target.value)}>
          <option value="">テンプレートから入力</option>
          {templates.map((t) => (
            <option key={t.name} value={t.name}>
              {t.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <input type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} />
        <input
          placeholder="摘要"
          maxLength={200}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>

      {lines.map((l, i) => (
        <div key={i}>
          <select
            value={l.side}
            onChange={(e) => updateLine(i, { side: e.target.value as Side })}
          >
            <option value="debit">借方</option>
            <option value="credit">貸方</option>
          </select>
          <select
            value={l.account}
            onChange={(e) => updateLine(i, { account: e.target.value })}
          >
            <option value="">勘定科目を選択</option>
            {accounts.map((a) => (
              <option key={a.name} value={a.name}>
                {a.name}（{a.category}）
              </option>
            ))}
          </select>
          <input
            type="number"
            placeholder="金額"
            value={l.amount || ""}
                        onChange={(e) => updateAmount(i, Number(e.target.value))}
          />
          {lines.length > 2 && (
            <button type="button" onClick={() => removeLine(i)}>削除</button>
          )}
        </div>
      ))}

      <button type="button" onClick={addLine}>行を追加</button>

      <p>
        借方合計 {debitTotal.toLocaleString()} ／ 貸方合計 {creditTotal.toLocaleString()}
        {isBalanced ? "（一致）" : "（不一致）"}
      </p>
      {hasSameAccount && <p>同じ勘定科目を借方と貸方の両方に使うことはできません</p>}

      <button type="submit" disabled={!isBalanced || !allSelected || hasSameAccount || submitting}>
        {submitting ? "送信中..." : "登録"}
      </button>
      {message && <p>{message}</p>}
    </form>
  )
}