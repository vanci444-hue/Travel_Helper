import { formatMoneyWan, type BudgetPublic } from '../../services/itineraryService'

export function BudgetPanel({ budget }: { budget: BudgetPublic }) {
  const categoryText = budget.categories.map((item) => item.label).join('、')
  return (
    <section className="report-section" aria-labelledby="budget-title">
      <h2 id="budget-title">💰 预算</h2>
      <p>
        {categoryText}合计约 {formatMoneyWan(budget.total_amount)}，上限 {formatMoneyWan(budget.cap_amount)}。
        {budget.over_cap ? '超出上限。' : '未超出上限。'}
      </p>
      <p className="report-note">{budget.includes_note}</p>
    </section>
  )
}
