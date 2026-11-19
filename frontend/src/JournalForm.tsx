import { useEffect, useState, type FormEvent } from "react"

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

const API_URL = "http://127.0.0.1:8000"

function emptyLine(side: Side): LineInput {
  return { account: "", side, amount: 0 }
}

export default function JournalForm({ onCreated }: Props) {
  const [entryDate, setEntryDate] = useState(new Date().toISOString().slice(0, 10))
  const [description, setDescription] = useState("")
  const [lines, setLines] = useState<LineInput[]>([emptyLine("debit"), emptyLine("credit")])
  const [message, setMessage] = useState<string | null>(null)
    const [accounts, setAccounts] = useState<Account[]>([])

  // 画面を開いたときに、バックエンドから勘定科目の一覧を取得
  useEffect(() => {
    fetch(`${API_URL}/accounts`)
      .then((res) => res.json())
      .then((json: Account[]) => setAccounts(json))
  }, [])

    const [templates, setTemplates] = useState<JournalTemplate[]>([])

  // 画面を開いたときに、テンプレートの一覧を取得
  useEffect(() => {
    fetch(`${API_URL}/templates`)
      .then((res) => res.json())
      .then((json: JournalTemplate[]) => setTemplates(json))
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

    const res = await fetch(`${API_URL}/journal-entries`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entry_date: entryDate, description, lines }),
    })

    if (res.ok) {
      setMessage("登録しました")
      setDescription("")
      setLines([emptyLine("debit"), emptyLine("credit")])
      onCreated()
    } else {
      const body = await res.json()
      const detail = body.detail
      const text =
        typeof detail === "string"
          ? detail
          : detail.map((d: { msg: string }) => d.msg).join(" / ")
      setMessage(`登録できませんでした：${text}`)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <h2>仕訳の入力</h2>
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

      <button type="submit" disabled={!isBalanced || !allSelected}>登録</button>
      {message && <p>{message}</p>}
    </form>
  )
}