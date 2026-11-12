type Account = {
  name: string
  category: string
}

const accounts: Account[] = [
  { name: "現金", category: "資産" },
  { name: "売掛金", category: "資産" },
  { name: "売上高", category: "収益" },
]

function App() {
  return (
    <div>
      <h1>記帳アプリ</h1>
      <ul>
        {accounts.map((a) => (
          <li key={a.name}>
            {a.name}（{a.category}）
          </li>
        ))}
      </ul>
    </div>
  )
}

export default App