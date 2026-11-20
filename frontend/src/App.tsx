import MonthlyChart from "./MonthlyChart"
import { useEffect, useState } from "react"
import JournalForm from "./JournalForm"


type TrialBalanceRow = {
  account: string
  category: string
  debit_balance: number
  credit_balance: number
  warning: string | null
}

type TrialBalance = {
  rows: TrialBalanceRow[]
  debit_total: number
  credit_total: number
  is_balanced: boolean
}

const API_URL = "http://127.0.0.1:8000"

function App() {
  const [data, setData] = useState<TrialBalance | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  // 仕訳が増えたときに、試算表とグラフの両方を更新する
  function refreshAll() {
    loadTrialBalance()
    setRefreshKey((k) => k + 1)
  }

  function loadTrialBalance() {
    fetch(`${API_URL}/trial-balance`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((json: TrialBalance) => {
        setData(json)
        setError(null)
      })
      .catch((e) => setError(String(e)))
  }

    async function loadDemoData() {
    const res = await fetch(`${API_URL}/demo-data`, { method: "POST" })
    if (res.ok) {
      refreshAll()
    } else {
      const body = await res.json()
      alert(body.detail)
    }
  }

  useEffect(() => {
    loadTrialBalance()
  }, [])

  return (
    <div>
      <h1>記帳アプリ</h1>

            <button onClick={loadDemoData}>サンプルデータを読み込む</button>

      <JournalForm onCreated={refreshAll} />
      
      <MonthlyChart refreshKey={refreshKey} />
      <h2>合計残高試算表</h2>
      {error && <p>エラー：{error}</p>}
      {!error && data === null && <p>読み込み中...</p>}
      {data && (
        <table>
          <thead>
            <tr>
              <th>科目</th>
              <th>分類</th>
              <th>借方残高</th>
              <th>貸方残高</th>
              <th>警告</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.account}>
                <td>{r.account}</td>
                <td>{r.category}</td>
                <td>{r.debit_balance.toLocaleString()}</td>
                <td>{r.credit_balance.toLocaleString()}</td>
                <td>{r.warning ?? ""}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={2}>合計</td>
              <td>{data.debit_total.toLocaleString()}</td>
              <td>{data.credit_total.toLocaleString()}</td>
              <td>{data.is_balanced ? "一致" : "不一致"}</td>
            </tr>
          </tfoot>
        </table>
      )}
    </div>
  )
}

export default App