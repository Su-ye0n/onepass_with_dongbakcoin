'use client'

import { useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowLeft, ArrowUp, LoaderCircle } from 'lucide-react'
import {
  api,
  type BenefitRule,
  type CardProduct,
  type CategoryPriority,
  type Merchant,
  type PaymentRecord,
  type UserCard,
} from '@/lib/api'

type LookupOption = { id: string; label: string }
type DetailField = { label: string; value: string | number | boolean | null | undefined }

function LookupSection<T>({
  title,
  options,
  emptyLabel,
  onLookup,
  getFields,
}: {
  title: string
  options: LookupOption[]
  emptyLabel: string
  onLookup: (id: string) => Promise<T>
  getFields: (item: T) => DetailField[]
}) {
  const [selectedId, setSelectedId] = useState(options[0]?.id ?? '')
  const [result, setResult] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!options.some((option) => option.id === selectedId)) {
      setSelectedId(options[0]?.id ?? '')
      setResult(null)
    }
  }, [options, selectedId])

  const lookup = async () => {
    if (!selectedId) return
    setPending(true)
    setError('')
    try {
      setResult(await onLookup(selectedId))
    } catch (cause) {
      setResult(null)
      setError(cause instanceof Error ? cause.message : '상세 정보를 불러오지 못했습니다.')
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="api-tool-section">
      <h3>{title}</h3>
      {options.length ? (
        <div className="api-tool-controls">
          <select
            aria-label={`${title} 선택`}
            value={selectedId}
            onChange={(event) => {
              setSelectedId(event.target.value)
              setResult(null)
              setError('')
            }}
          >
            {options.map((option) => (
              <option key={option.id} value={option.id}>{option.label}</option>
            ))}
          </select>
          <button type="button" disabled={pending || !selectedId} onClick={() => void lookup()}>
            {pending ? '조회 중…' : '상세 조회'}
          </button>
        </div>
      ) : <p className="api-tool-muted">{emptyLabel}</p>}
      {error && <p className="api-tool-error" role="alert">{error}</p>}
      {result !== null && (
        <dl className="api-tool-details">
          {getFields(result).filter((field) => field.value != null).map((field) => (
            <div key={field.label}>
              <dt>{field.label}</dt>
              <dd>{String(field.value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}

function moveItem<T>(items: T[], index: number, offset: number): T[] {
  const target = index + offset
  if (target < 0 || target >= items.length) return items
  const reordered = [...items]
  ;[reordered[index], reordered[target]] = [reordered[target], reordered[index]]
  return reordered
}

function sortedCategoryItems(items: CategoryPriority[]): CategoryPriority[] {
  return [...items].sort(
    (left, right) =>
      left.user_category_code.localeCompare(right.user_category_code) ||
      (left.priority_group ?? Number.MAX_SAFE_INTEGER) -
        (right.priority_group ?? Number.MAX_SAFE_INTEGER),
  )
}

export default function ApiToolsPanel({
  userId,
  products,
  cards,
  merchants,
  payments,
  benefits,
  onBack,
  onRefresh,
}: {
  userId: string
  products: CardProduct[]
  cards: UserCard[]
  merchants: Merchant[]
  payments: PaymentRecord[]
  benefits: Record<string, BenefitRule[]>
  onBack: () => void
  onRefresh: () => Promise<void>
}) {
  const [databaseStatus, setDatabaseStatus] = useState('')
  const [databaseError, setDatabaseError] = useState('')
  const [cardPriorities, setCardPriorities] = useState<UserCard[]>([])
  const [categoryPriorities, setCategoryPriorities] = useState<CategoryPriority[]>([])
  const [priorityError, setPriorityError] = useState('')
  const [categoryError, setCategoryError] = useState('')
  const [savingCards, setSavingCards] = useState(false)
  const [savingCategories, setSavingCategories] = useState(false)
  const [cardSaved, setCardSaved] = useState(false)
  const [categorySaved, setCategorySaved] = useState(false)
  const [loadingSettings, setLoadingSettings] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    const loadSettings = async () => {
      const [health, cardRanks, categoryRanks] = await Promise.allSettled([
        api.checkDatabase({ signal: controller.signal }),
        api.getCardPriorities(userId, { signal: controller.signal }),
        api.getCategoryPriorities(userId, { signal: controller.signal }),
      ])
      if (!active) return
      if (health.status === 'fulfilled') {
        setDatabaseStatus(`${health.value.status} · ${health.value.database}`)
        setDatabaseError('')
      } else {
        setDatabaseStatus('')
        setDatabaseError(health.reason instanceof Error ? health.reason.message : 'DB 상태 조회 실패')
      }
      if (cardRanks.status === 'fulfilled') {
        setCardPriorities(cardRanks.value)
        setPriorityError('')
      } else {
        setCardPriorities([])
        setPriorityError(cardRanks.reason instanceof Error ? cardRanks.reason.message : '카드 우선순위 조회 실패')
      }
      if (categoryRanks.status === 'fulfilled') {
        setCategoryPriorities(sortedCategoryItems(categoryRanks.value))
        setCategoryError('')
      } else {
        setCategoryPriorities([])
        setCategoryError(categoryRanks.reason instanceof Error ? categoryRanks.reason.message : '업종별 우선순위 조회 실패')
      }
      setLoadingSettings(false)
    }
    void loadSettings()
    return () => {
      active = false
      controller.abort()
    }
  }, [userId])

  const benefitRules = useMemo(() => Object.values(benefits).flat(), [benefits])
  const groupedCategoryPriorities = useMemo(() => {
    const grouped = new Map<string, CategoryPriority[]>()
    for (const priority of sortedCategoryItems(categoryPriorities)) {
      const group = grouped.get(priority.user_category_code) ?? []
      group.push(priority)
      grouped.set(priority.user_category_code, group)
    }
    return [...grouped.entries()]
  }, [categoryPriorities])

  const saveCardPriorities = async () => {
    setSavingCards(true)
    setPriorityError('')
    setCardSaved(false)
    try {
      const saved = await api.updateCardPriorities(
        userId,
        cardPriorities.map((card, index) => ({
          user_card_id: card.user_card_id,
          priority: index + 1,
        })),
      )
      setCardPriorities(saved)
      setCardSaved(true)
      await onRefresh()
    } catch (cause) {
      setPriorityError(cause instanceof Error ? cause.message : '카드 우선순위를 저장하지 못했습니다.')
    } finally {
      setSavingCards(false)
    }
  }

  const saveCategoryPriorities = async () => {
    setSavingCategories(true)
    setCategoryError('')
    setCategorySaved(false)
    try {
      const priorities = groupedCategoryPriorities.flatMap(([code, entries]) =>
        entries.map((entry, index) => ({
          user_category_code: code,
          user_card_id: entry.user_card_id,
          priority_group: index + 1,
        })),
      )
      const saved = await api.updateCategoryPriorities(userId, priorities)
      setCategoryPriorities(sortedCategoryItems(saved))
      setCategorySaved(true)
    } catch (cause) {
      setCategoryError(cause instanceof Error ? cause.message : '업종별 우선순위를 저장하지 못했습니다.')
    } finally {
      setSavingCategories(false)
    }
  }

  const cardName = (userCardId: string) => {
    const card = cards.find((item) => item.user_card_id === userCardId)
    return products.find((item) => item.product_id === card?.product_id)?.product_name
      ?? card?.product_id
      ?? userCardId
  }

  const productsOptions = products.map(({ product_id, product_name }) => ({
    id: product_id,
    label: product_name,
  }))
  const cardsOptions = cards.map((card) => ({
    id: card.user_card_id,
    label: cardName(card.user_card_id),
  }))
  const merchantOptions = merchants.map((merchant) => ({
    id: merchant.merchant_id,
    label: merchant.merchant_name ?? merchant.merchant_id,
  }))
  const benefitOptions = benefitRules.map((rule) => ({
    id: rule.rule_id,
    label: rule.benefit_name ?? rule.rule_id,
  }))
  const paymentOptions = payments.map((payment) => ({
    id: payment.tx_id,
    label: `${payment.merchant_name ?? payment.tx_id} · ${payment.event_at}`,
  }))

  return (
    <div className="screen-content api-tools-screen">
      <div className="detail-head">
        <button onClick={onBack} aria-label="뒤로"><ArrowLeft size={19} /></button>
        <strong>API 기능 관리</strong>
        <span className="verified">백엔드 API</span>
      </div>

      <section className="api-tool-section api-health">
        <h3>데이터베이스 연결 상태</h3>
        {loadingSettings && !databaseStatus && <LoaderCircle className="spin" size={18} />}
        {databaseStatus && <p role="status">{databaseStatus}</p>}
        {databaseError && <p className="api-tool-error" role="alert">{databaseError}</p>}
      </section>

      <section className="api-tool-section">
        <h3>카드 우선순위</h3>
        <p className="api-tool-muted">결제 추천에서 먼저 고려할 보유 카드 순서를 설정합니다.</p>
        {cardPriorities.map((card, index) => (
          <div className="api-tool-rank" key={card.user_card_id}>
            <b>{index + 1}. {cardName(card.user_card_id)}</b>
            <div>
              <button aria-label={`${cardName(card.user_card_id)} 위로`} disabled={index === 0 || savingCards} onClick={() => setCardPriorities((current) => moveItem(current, index, -1))}><ArrowUp size={16} /></button>
              <button aria-label={`${cardName(card.user_card_id)} 아래로`} disabled={index === cardPriorities.length - 1 || savingCards} onClick={() => setCardPriorities((current) => moveItem(current, index, 1))}><ArrowDown size={16} /></button>
            </div>
          </div>
        ))}
        {!loadingSettings && !cardPriorities.length && !priorityError && <p className="api-tool-muted">설정할 보유 카드가 없습니다.</p>}
        {priorityError && <p className="api-tool-error" role="alert">{priorityError}</p>}
        {cardSaved && <p className="api-tool-success" role="status">카드 우선순위를 저장했습니다.</p>}
        <button className="api-tool-save" disabled={savingCards || !cardPriorities.length} onClick={() => void saveCardPriorities()}>{savingCards ? '저장 중…' : '카드 우선순위 저장'}</button>
      </section>

      <section className="api-tool-section">
        <h3>업종별 카드 우선순위</h3>
        <p className="api-tool-muted">등록된 카테고리별 카드 순서를 변경합니다.</p>
        {groupedCategoryPriorities.map(([code, entries]) => (
          <div className="api-category-group" key={code}>
            <b>{code}</b>
            {entries.map((entry, index) => (
              <div className="api-tool-rank" key={entry.priority_id}>
                <span>{index + 1}. {cardName(entry.user_card_id)}</span>
                <div>
                  <button aria-label={`${code} ${cardName(entry.user_card_id)} 위로`} disabled={index === 0 || savingCategories} onClick={() => setCategoryPriorities((current) => {
                    const group = sortedCategoryItems(current).filter((item) => item.user_category_code === code)
                    const reordered = moveItem(group, index, -1)
                    return sortedCategoryItems([...current.filter((item) => item.user_category_code !== code), ...reordered])
                  })}><ArrowUp size={16} /></button>
                  <button aria-label={`${code} ${cardName(entry.user_card_id)} 아래로`} disabled={index === entries.length - 1 || savingCategories} onClick={() => setCategoryPriorities((current) => {
                    const group = sortedCategoryItems(current).filter((item) => item.user_category_code === code)
                    const reordered = moveItem(group, index, 1)
                    return sortedCategoryItems([...current.filter((item) => item.user_category_code !== code), ...reordered])
                  })}><ArrowDown size={16} /></button>
                </div>
              </div>
            ))}
          </div>
        ))}
        {!loadingSettings && !groupedCategoryPriorities.length && !categoryError && <p className="api-tool-muted">저장된 업종별 우선순위가 없습니다.</p>}
        {categoryError && <p className="api-tool-error" role="alert">{categoryError}</p>}
        {categorySaved && <p className="api-tool-success" role="status">업종별 우선순위를 저장했습니다.</p>}
        <button className="api-tool-save" disabled={savingCategories || !categoryPriorities.length} onClick={() => void saveCategoryPriorities()}>{savingCategories ? '저장 중…' : '업종별 우선순위 저장'}</button>
      </section>

      <h2 className="api-tool-heading">상세 조회 API</h2>
      <LookupSection
        title="카드 상품 상세"
        options={productsOptions}
        emptyLabel="조회할 카드 상품이 없습니다."
        onLookup={api.getProduct}
        getFields={(item) => [
          { label: '상품 ID', value: item.product_id },
          { label: '상품명', value: item.product_name },
          { label: '카드사', value: item.issuer },
          { label: '카드 종류', value: item.card_type },
          { label: '상태', value: item.product_status },
          { label: '약관 버전', value: item.terms_version },
          { label: '원본 상태', value: item.source_status },
          { label: '원본 참조', value: item.source_ref },
        ]}
      />
      <LookupSection
        title="보유 카드 상세"
        options={cardsOptions}
        emptyLabel="상세 조회할 보유 카드가 없습니다."
        onLookup={(id) => api.getUserCard(userId, id)}
        getFields={(item) => [
          { label: '보유 카드 ID', value: item.user_card_id },
          { label: '상품 ID', value: item.product_id },
          { label: '상태', value: item.card_status },
          { label: '우선순위', value: item.default_preference_rank },
          { label: '신용 한도', value: item.credit_limit_won },
          { label: '만료일', value: item.expires_at },
        ]}
      />
      <LookupSection
        title="가맹점 상세"
        options={merchantOptions}
        emptyLabel="조회할 가맹점이 없습니다."
        onLookup={api.getMerchant}
        getFields={(item) => [
          { label: '가맹점 ID', value: item.merchant_id },
          { label: '가맹점명', value: item.merchant_name },
          { label: '업종 코드', value: item.industry_code },
          { label: '동백전 상태', value: item.dongbaek_status },
          { label: '매출 구간', value: item.sales_band },
          { label: 'QR 가맹점', value: item.is_qr_merchant },
          { label: '동백플러스 할인율', value: item.dbplus_discount_rate },
          { label: '지역 코드', value: item.region_code },
        ]}
      />
      <LookupSection
        title="카드 혜택 상세"
        options={benefitOptions}
        emptyLabel="조회할 혜택 규칙이 없습니다."
        onLookup={api.getBenefitRule}
        getFields={(item) => [
          { label: '규칙 ID', value: item.rule_id },
          { label: '카드 상품 ID', value: item.product_id },
          { label: '혜택명', value: item.benefit_name },
          { label: '혜택 종류', value: item.benefit_type },
          { label: '적립률', value: item.rate },
          { label: '고정 혜택', value: item.fixed_amount_won },
          { label: '최소 결제 금액', value: item.min_amount_won },
          { label: '1회 한도', value: item.per_tx_cap_won },
          { label: '월 한도', value: item.monthly_cap_won },
          { label: '월 횟수 제한', value: item.monthly_count_cap },
          { label: '유효 기간', value: [item.valid_from, item.valid_to].filter(Boolean).join(' ~ ') },
        ]}
      />
      <LookupSection
        title="결제 상세"
        options={paymentOptions}
        emptyLabel="조회할 결제 이력이 없습니다."
        onLookup={api.getPaymentDetail}
        getFields={(item) => [
          { label: '거래 ID', value: item.tx_id },
          { label: '가맹점명', value: item.merchant_name },
          { label: '카드 상품', value: item.product_name },
          { label: '결제 금액', value: item.amount_won },
          { label: '승인 상태', value: item.approval_status },
          { label: '혜택 금액', value: item.awarded_benefit_won },
          { label: '결제 시각', value: item.event_at },
          { label: '거래 메모', value: item.event_note },
        ]}
      />
    </div>
  )
}
