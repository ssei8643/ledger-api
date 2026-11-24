import MonthlyChart from "./MonthlyChart"
import { useEffect, useState } from "react"
import JournalForm from "./JournalForm"
import BankImport from "./BankImport"
import FinancialStatements from "./FinancialStatements"
import { API_URL, detailText, errorMessage, getJson } from "./api"


type TrialBalanceRow = {
  account: string
  category: string
  debit_total: number
  credit_total: number
  debit_balance: number
  credit_balance: number
  warning: string | null
}

type TrialBalance = {
  rows: TrialBalanceRow[]
  debit_total: number
  credit_total: number
  debit_balance_total: number
  credit_balance_total: number
  is_balanced: boolean
}

// 0円の欄は空欄にして、金額のある欄を読みやすくする
function yen(amount: number): string {
  return amount === 0 ? "" : amount.toLocaleString()
}

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
    getJson<TrialBalance>("/trial-balance")
      .then((json) => {
        setData(json)
        setError(null)
      })
      .catch((e) => setError(errorMessage(e)))
  }

  async function loadDemoData() {
    try {
      const res = await fetch(`${API_URL}/demo-data`, { method: "POST" })
      if (res.ok) {
        refreshAll()
      } else {
        alert(await detailText(res))
      }
    } catch (e) {
      alert(errorMessage(e))
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
      <BankImport onImported={refreshAll} />
      
      <MonthlyChart refreshKey={refreshKey} />
      <h2>合計残高試算表</h2>
      {error && <p>エラー：{error}</p>}
      {!error && data === null && <p>読み込み中...</p>}
      {data && (
        <table>
          <thead>
            <tr>
              <th>借方合計</th>
              <th>借方残高</th>
              <th>科目</th>
              <th>分類</th>
              <th>貸方残高</th>
              <th>貸方合計</th>
              <th>警告</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.account}>
                <td className="num">{yen(r.debit_total)}</td>
                <td className="num">{yen(r.debit_balance)}</td>
                <td className="num">{r.account}</td>
                <td className="num">{r.category}</td>
                <td className="num">{yen(r.credit_balance)}</td>
                <td className="num">{yen(r.credit_total)}</td>
                <td className="num">{r.warning ?? ""}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td className="num">{data.debit_total.toLocaleString()}</td>
              <td className="num">{data.debit_balance_total.toLocaleString()}</td>
              <td colSpan={2}>合計</td>
              <td className="num">{data.credit_balance_total.toLocaleString()}</td>
              <td className="num">{data.credit_total.toLocaleString()}</td>
              <td className="num">{data.is_balanced ? "一致" : "不一致"}</td>
            </tr>
          </tfoot>
        </table>
      )}
    <FinancialStatements refreshKey={refreshKey} />
    </div>
  )
}

export default App