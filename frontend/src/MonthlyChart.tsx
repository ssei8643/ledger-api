import { useEffect, useState } from "react"
import { Bar, BarChart, CartesianGrid, Legend, Tooltip, XAxis, YAxis } from "recharts"

type MonthlySummary = {
  month: string
  revenue: number
  expense: number
  net_income: number
}

type Props = {
  refreshKey: number
}

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000"

export default function MonthlyChart({ refreshKey }: Props) {
  const [data, setData] = useState<MonthlySummary[]>([])

  // refreshKey が変わるたびに（＝仕訳が登録されるたびに）取得し直す
  useEffect(() => {
    fetch(`${API_URL}/monthly-summary`)
      .then((res) => res.json())
      .then((json: MonthlySummary[]) => setData(json))
  }, [refreshKey])

  return (
    <div>
      <h2>月別の収益・費用</h2>
      {data.length === 0 ? (
        <p>まだ収益・費用の仕訳がありません</p>
      ) : (
        <BarChart width={640} height={300} data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="month" />
          {/* 260,000 のような桁数の多い金額が切れないよう、軸の幅を広げる */}
          <YAxis width={80} tickFormatter={(v: number) => v.toLocaleString()} />
          <Tooltip />
          <Legend />
          <Bar dataKey="revenue" name="収益" fill="#4a90d9" />
          <Bar dataKey="expense" name="費用" fill="#e57373" />
          <Bar dataKey="net_income" name="純利益" fill="#81c784" />
        </BarChart>
      )}
    </div>
  )
}