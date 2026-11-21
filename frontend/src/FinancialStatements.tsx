import { useEffect, useState } from "react"

type Item = {
  account: string
  amount: number
}

type FinancialStatementsData = {
  income_statement: {
    revenues: Item[]
    expenses: Item[]
    total_revenue: number
    total_expense: number
    net_income: number
  }
  balance_sheet: {
    assets: Item[]
    liabilities: Item[]
    equity: Item[]
    net_income: number
    total_assets: number
    total_liabilities_and_equity: number
    is_balanced: boolean
  }
}

type Props = {
  refreshKey: number
}

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000"

function ItemRows({ items }: { items: Item[] }) {
  return (
    <>
      {items.map((i) => (
        <tr key={i.account}>
          <td>{i.account}</td>
          <td>{i.amount.toLocaleString()}</td>
        </tr>
      ))}
    </>
  )
}

export default function FinancialStatements({ refreshKey }: Props) {
  const [data, setData] = useState<FinancialStatementsData | null>(null)

  useEffect(() => {
    fetch(`${API_URL}/financial-statements`)
      .then((res) => res.json())
      .then((json: FinancialStatementsData) => setData(json))
  }, [refreshKey])

  if (data === null) return null
  const pl = data.income_statement
  const bs = data.balance_sheet

  return (
    <div>
      <h2>損益計算書</h2>
      <table>
        <tbody>
          <tr><th colSpan={2}>収益</th></tr>
          <ItemRows items={pl.revenues} />
          <tr><td>収益合計</td><td>{pl.total_revenue.toLocaleString()}</td></tr>
          <tr><th colSpan={2}>費用</th></tr>
          <ItemRows items={pl.expenses} />
          <tr><td>費用合計</td><td>{pl.total_expense.toLocaleString()}</td></tr>
          <tr><th>当期純利益</th><th>{pl.net_income.toLocaleString()}</th></tr>
        </tbody>
      </table>

      <h2>貸借対照表</h2>
      <table>
        <tbody>
          <tr><th colSpan={2}>資産</th></tr>
          <ItemRows items={bs.assets} />
          <tr><th>資産合計</th><th>{bs.total_assets.toLocaleString()}</th></tr>
          <tr><th colSpan={2}>負債</th></tr>
          <ItemRows items={bs.liabilities} />
          <tr><th colSpan={2}>純資産</th></tr>
          <ItemRows items={bs.equity} />
          <tr><td>当期純利益</td><td>{bs.net_income.toLocaleString()}</td></tr>
          <tr><th>負債・純資産合計</th><th>{bs.total_liabilities_and_equity.toLocaleString()}</th></tr>
        </tbody>
      </table>
      <p>{bs.is_balanced ? "資産と負債・純資産の合計は一致しています" : "資産と負債・純資産の合計が一致していません"}</p>
    </div>
  )
}