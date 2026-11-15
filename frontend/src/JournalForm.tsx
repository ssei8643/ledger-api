import { useState, type FormEvent } from "react"

type Side = "debit" | "credit"

type LineInput = {
  account: string
  side: Side
  amount: number
}

type Props = {
  onCreated: () => void
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

  // 入力中の借方・貸方の合計（画面上でリアルタイムに計算）
  const debitTotal = lines.filter((l) => l.side === "debit").reduce((sum, l) => sum + l.amount, 0)
  const creditTotal = lines.filter((l) => l.side === "credit").reduce((sum, l) => sum + l.amount, 0)
  const isBalanced = debitTotal > 0 && debitTotal === creditTotal

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
          <input
            placeholder="勘定科目"
            value={l.account}
            onChange={(e) => updateLine(i, { account: e.target.value })}
          />
          <input
            type="number"
            placeholder="金額"
            value={l.amount || ""}
            onChange={(e) => updateLine(i, { amount: Number(e.target.value) })}
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

      <button type="submit" disabled={!isBalanced}>登録</button>
      {message && <p>{message}</p>}
    </form>
  )
}