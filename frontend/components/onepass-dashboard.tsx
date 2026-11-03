'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  BarChart3,
  CreditCard,
  Home,
  LoaderCircle,
  Store,
  WalletCards,
} from 'lucide-react'
import {
  api,
  DEMO_USER_ID,
  type BenefitRule,
  type CardProduct,
  type Merchant,
  type PaymentRecord,
  type PaymentRecommendation,
  type UserCard,
} from '@/lib/api'

type Screen = 'home' | 'pay' | 'cards' | 'report'

const formatWon = (amount: number) => `${amount.toLocaleString('ko-KR')}원`

export default function OnePassDashboard() {
  const [screen, setScreen] = useState<Screen>('home')
  const [products, setProducts] = useState<CardProduct[]>([])
  const [userCards, setUserCards] = useState<UserCard[]>([])
  const [merchants, setMerchants] = useState<Merchant[]>([])
  const [payments, setPayments] = useState<PaymentRecord[]>([])
  const [benefits, setBenefits] = useState<Record<string, BenefitRule[]>>({})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [pendingCard, setPendingCard] = useState('')

  const loadData = useCallback(async () => {
    try {
      const [loadedProducts, loadedCards, loadedMerchants, history] =
        await Promise.all([
          api.getProducts(),
          api.getUserCards(DEMO_USER_ID),
          api.getMerchants(),
          api.getPaymentHistory(DEMO_USER_ID),
        ])
      setProducts(loadedProducts)
      setUserCards(loadedCards)
      setMerchants(loadedMerchants)
      setPayments(history.payments)
      setError('')
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : '서비스 정보를 불러오지 못했습니다.',
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  useEffect(() => {
    if (!products.length) return
    let active = true
    Promise.all(
      products.map(async (product) => [
        product.product_id,
        await api.getBenefits(product.product_id),
      ] as const),
    )
      .then((entries) => {
        if (active) setBenefits(Object.fromEntries(entries))
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(
            cause instanceof Error
              ? cause.message
              : '카드 혜택 정보를 불러오지 못했습니다.',
          )
        }
      })
    return () => {
      active = false
    }
  }, [products])

  const handleCardToggle = async (product: CardProduct) => {
    const activeCard = userCards.find(
      (card) =>
        card.product_id === product.product_id &&
        card.card_status === 'ACTIVE',
    )
    setPendingCard(product.product_id)
    try {
      if (activeCard) {
        await api.removeUserCard(DEMO_USER_ID, activeCard.user_card_id)
      } else {
        await api.addUserCard(DEMO_USER_ID, product.product_id)
      }
      await loadData()
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : '카드 설정을 저장하지 못했습니다.',
      )
    } finally {
      setPendingCard('')
    }
  }

  const activePayments = useMemo(
    () =>
      payments
        .filter((payment) => payment.approval_status === 'APPROVED')
        .sort(
          (left, right) =>
            Date.parse(right.event_at) - Date.parse(left.event_at),
        ),
    [payments],
  )

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand">
          <div className="brand-mark"><span className="brand-symbol">동</span></div>
          <div><b>동백원카드</b><span>부산시민 원패스</span></div>
        </div>
        <span className="user-id">사용자 {DEMO_USER_ID}</span>
      </header>

      <nav className="tab-bar" aria-label="주요 메뉴">
        <button className={screen === 'home' ? 'active' : ''} onClick={() => setScreen('home')}><Home size={17} />홈</button>
        <button className={screen === 'pay' ? 'active' : ''} onClick={() => setScreen('pay')}><Store size={17} />결제 추천</button>
        <button className={screen === 'cards' ? 'active' : ''} onClick={() => setScreen('cards')}><WalletCards size={17} />내 카드</button>
        <button className={screen === 'report' ? 'active' : ''} onClick={() => setScreen('report')}><BarChart3 size={17} />결제 내역</button>
      </nav>

      <div className="app-body">
        {error && (
          <div className="api-alert" role="alert">
            <span>{error}</span>
            <button onClick={() => void loadData()}>다시 시도</button>
          </div>
        )}
        {loading ? (
          <div className="api-loading"><LoaderCircle className="spin" size={22} /> API 데이터를 불러오는 중입니다.</div>
        ) : (
          <>
            {screen === 'home' && (
              <HomeScreen
                payments={activePayments}
                cardCount={userCards.filter((card) => card.card_status === 'ACTIVE').length}
                onNavigate={setScreen}
              />
            )}
            {screen === 'pay' && (
              <PaymentScreen
                merchants={merchants}
                userCards={userCards}
                userId={DEMO_USER_ID}
                onPaymentComplete={loadData}
                onError={setError}
              />
            )}
            {screen === 'cards' && (
              <CardScreen
                products={products}
                userCards={userCards}
                benefits={benefits}
                pendingCard={pendingCard}
                onToggle={handleCardToggle}
              />
            )}
            {screen === 'report' && <PaymentHistoryScreen payments={activePayments} />}
          </>
        )}
      </div>
      <footer className="app-footer">
        <span>Dongbaek OnePass API</span>
        <span>DEMO · 실제 금융 결제 아님</span>
      </footer>
    </main>
  )
}

function HomeScreen({
  payments,
  cardCount,
  onNavigate,
}: {
  payments: PaymentRecord[]
  cardCount: number
  onNavigate: (screen: Screen) => void
}) {
  const recent = payments[0]
  const total = payments.reduce((sum, payment) => sum + payment.amount_won, 0)
  return (
    <div className="screen-content">
      <div className="user-row"><div className="avatar">동</div><strong>안녕하세요!</strong><span className="home-caption">연결된 카드 {cardCount}장</span></div>
      <section className="balance-card api-summary">
        <div className="balance-top"><span>API 결제 합계</span><span>승인 완료</span></div>
        <strong>{formatWon(total)}</strong>
        <div className="pass"><span>결제 내역</span><b>{payments.length}건</b></div>
      </section>
      <button className="api-action" onClick={() => onNavigate('pay')}>
        <span><Store size={18} /> 결제 추천 받기</span><b>가맹점과 금액에 맞는 카드를 찾아요</b>
      </button>
      <button className="api-action secondary" onClick={() => onNavigate('cards')}>
        <span><CreditCard size={18} /> 내 카드 관리</span><b>API에서 카드 상품과 연결 상태를 확인해요</b>
      </button>
      <section className="api-panel">
        <div className="chart-heading"><div><b>최근 승인 내역</b><small>백엔드 결제 이력 API</small></div><button onClick={() => onNavigate('report')}>전체 보기 ›</button></div>
        {recent ? (
          <div className="recent-payment">
            <div><b>{recent.merchant_name ?? '가맹점'}</b><small>{recent.product_name ?? '카드'} · {new Date(recent.event_at).toLocaleDateString('ko-KR')}</small></div>
            <strong>{formatWon(recent.amount_won)}</strong>
          </div>
        ) : <p className="empty-state">아직 승인된 결제 내역이 없습니다.</p>}
      </section>
    </div>
  )
}

function PaymentScreen({
  merchants,
  userCards,
  userId,
  onPaymentComplete,
  onError,
}: {
  merchants: Merchant[]
  userCards: UserCard[]
  userId: string
  onPaymentComplete: () => Promise<void>
  onError: (message: string) => void
}) {
  const eligibleCards = userCards.filter((card) => card.card_status === 'ACTIVE')
  const [merchantId, setMerchantId] = useState('')
  const [amount, setAmount] = useState('12000')
  const [recommendation, setRecommendation] = useState<PaymentRecommendation | null>(null)
  const [recommendationError, setRecommendationError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isPaying, setIsPaying] = useState(false)
  const [success, setSuccess] = useState('')

  useEffect(() => {
    if (!merchantId && merchants.length) setMerchantId(merchants[0].merchant_id)
  }, [merchantId, merchants])

  useEffect(() => {
    setRecommendation(null)
    setIsLoading(false)
    const amountWon = Number(amount)
    if (!merchantId || !Number.isInteger(amountWon) || amountWon <= 0) {
      setRecommendationError('')
      return
    }
    let active = true
    const timer = window.setTimeout(() => {
      setIsLoading(true)
      setRecommendationError('')
      api.recommendPayment({
        user_id: userId,
        merchant_id: merchantId,
        amount_won: amountWon,
      })
        .then((result) => {
          if (active) {
            setRecommendation(result)
          }
        })
        .catch((cause: unknown) => {
          if (active) {
            setRecommendation(null)
            setRecommendationError(
              cause instanceof Error ? cause.message : '결제 추천을 불러오지 못했습니다.',
            )
          }
        })
        .finally(() => {
          if (active) setIsLoading(false)
        })
    }, 250)
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [amount, merchantId, onError, userId])

  const handlePay = async () => {
    if (!recommendation?.recommended_user_card_id) return
    setIsPaying(true)
    setSuccess('')
    try {
      const result = await api.createPayment({
        request_id: crypto.randomUUID(),
        user_id: userId,
        user_card_id: recommendation.recommended_user_card_id,
        merchant_id: merchantId,
        amount_won: Number(amount),
      })
      setSuccess(`모의 결제가 승인되었습니다. 거래 ID: ${result.tx_id}`)
      await onPaymentComplete()
    } catch (cause) {
      onError(cause instanceof Error ? cause.message : '모의 결제가 실패했습니다.')
    } finally {
      setIsPaying(false)
    }
  }

  return (
    <div className="screen-content">
      <div className="detail-head"><strong>결제 추천</strong><span className="verified">추천 API 연결됨</span></div>
      <section className="api-panel">
        <label className="form-field">가맹점
          <select value={merchantId} onChange={(event) => { setMerchantId(event.target.value); setSuccess('') }}>
            {!merchants.length && <option value="">가맹점 데이터 없음</option>}
            {merchants.map((merchant) => <option key={merchant.merchant_id} value={merchant.merchant_id}>{merchant.merchant_name ?? merchant.merchant_id}</option>)}
          </select>
        </label>
        <label className="form-field">결제 금액
          <div className="amount-input"><input aria-label="결제 금액" inputMode="numeric" value={amount} onChange={(event) => { setAmount(event.target.value.replace(/[^0-9]/g, '')); setSuccess('') }} /><b>원</b></div>
        </label>
      </section>

      <section className="api-panel recommendation-panel">
        <div className="chart-heading"><div><b>추천 결과</b><small>보유 카드와 가맹점 혜택 기준</small></div>{isLoading && <LoaderCircle className="spin" size={18} />}</div>
        {recommendation ? (
          <>
            {recommendation.candidates.map((candidate) => (
              <div className={`candidate-row ${candidate.user_card_id === recommendation.recommended_user_card_id ? 'best' : ''}`} key={candidate.user_card_id}>
                <div><b>{candidate.product_name ?? candidate.product_id ?? '연결 카드'}</b><small>{candidate.reason ?? (candidate.eligible ? '결제 가능' : '혜택 대상 아님')}</small></div>
                <strong>{formatWon(candidate.expected_benefit_won)}</strong>
              </div>
            ))}
            {!recommendation.candidates.length && <p className="empty-state">추천 가능한 카드가 없습니다.</p>}
            <div className="recommend-total">예상 혜택 <strong>{formatWon(recommendation.expected_benefit_won)}</strong></div>
          </>
        ) : (
          <p className="empty-state">{recommendationError || (eligibleCards.length ? '추천 결과를 불러오는 중이거나 해당 조건의 추천이 없습니다.' : '먼저 내 카드에서 사용할 카드를 연결해 주세요.')}</p>
        )}
        <button className="primary-action" disabled={isPaying || !recommendation?.recommended_user_card_id} onClick={() => void handlePay()}>
          {isPaying ? '처리 중…' : '추천 카드로 모의 결제'}
        </button>
        {success && <p className="success-message" role="status">{success}</p>}
        <p className="recharge-note">이 기능은 백엔드 모의 결제 API만 호출하며 실제 계좌 출금·카드 승인은 발생하지 않습니다.</p>
      </section>
    </div>
  )
}

function CardScreen({
  products,
  userCards,
  benefits,
  pendingCard,
  onToggle,
}: {
  products: CardProduct[]
  userCards: UserCard[]
  benefits: Record<string, BenefitRule[]>
  pendingCard: string
  onToggle: (product: CardProduct) => void
}) {
  return (
    <div className="screen-content">
      <div className="detail-head"><strong>내 카드 관리</strong><span className="verified">카드 API 연결됨</span></div>
      <p className="list-label">카드 상품 {products.length}종 · 연결된 카드 {userCards.filter((card) => card.card_status === 'ACTIVE').length}장</p>
      <section className="card-list">
        {products.map((product) => {
          const userCard = userCards.find((card) => card.product_id === product.product_id && card.card_status === 'ACTIVE')
          const rules = benefits[product.product_id] ?? []
          return (
            <div className="card-row api-card-row" key={product.product_id}>
              <div className="api-card-info">
                <b>{product.product_name}</b>
                <small>{product.issuer ?? '카드사 정보 없음'} · {rules.length ? rules.map((rule) => rule.benefit_name ?? rule.benefit_type ?? '혜택').join(', ') : '등록된 혜택 정보 없음'}</small>
              </div>
              <button
                className={`toggle ${userCard ? 'on' : ''}`}
                aria-pressed={Boolean(userCard)}
                aria-label={`${product.product_name} ${userCard ? '연결 해제' : '연결'}`}
                disabled={pendingCard === product.product_id}
                onClick={() => onToggle(product)}
              >
                {pendingCard === product.product_id ? <LoaderCircle className="spin toggle-spinner" size={15} /> : <span />}
              </button>
            </div>
          )
        })}
        {!products.length && <p className="empty-state">조회된 카드 상품이 없습니다.</p>}
      </section>
    </div>
  )
}

function PaymentHistoryScreen({ payments }: { payments: PaymentRecord[] }) {
  const total = payments.reduce((sum, payment) => sum + payment.amount_won, 0)
  const benefits = payments.reduce((sum, payment) => sum + (payment.awarded_benefit_won ?? 0), 0)
  return (
    <div className="screen-content">
      <div className="detail-head"><strong>결제 내역</strong><span className="verified">결제 이력 API 연결됨</span></div>
      <section className="report-summary api-report-summary">
        <div><span>승인 건수</span><strong>{payments.length}건</strong><small>승인 결제 합계 {formatWon(total)}</small></div>
        <div className="report-ring"><b>{formatWon(benefits)}</b><span>적립 혜택</span></div>
      </section>
      <section className="api-panel history-list">
        {payments.map((payment) => (
          <article className="recent-payment" key={payment.tx_id}>
            <div><b>{payment.merchant_name ?? payment.merchant_id}</b><small>{payment.product_name ?? '카드'} · {new Date(payment.event_at).toLocaleString('ko-KR')}</small></div>
            <strong>{formatWon(payment.amount_won)}</strong>
          </article>
        ))}
        {!payments.length && <p className="empty-state">표시할 결제 내역이 없습니다.</p>}
      </section>
    </div>
  )
}
