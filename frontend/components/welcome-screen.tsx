'use client'

import { ArrowLeft, ArrowRight, CreditCard, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type TransitionEvent } from 'react'
import DongiImage from '@/components/dongi-image'

const cards = [
  {
    variant: 'big' as const,
    title: 'OnePass 동백전',
    imageAlt: '동이 캐릭터가 그려진 OnePass 동백전 카드',
  },
  {
    variant: 'classic' as const,
    title: 'OnePass 카드',
    imageAlt: '동이 캐릭터가 그려진 OnePass 카드',
  },
  {
    variant: 'daray' as const,
    title: 'OnePass 혜택 카드',
    imageAlt: '동이 캐릭터와 함께 보는 OnePass 혜택 안내',
  },
  {
    variant: 'rope' as const,
    title: '동이 캐릭터 카드',
    imageAlt: '동이 캐릭터 소개 카드',
  },
]

export default function WelcomeScreen({
  onLogin,
  notice,
}: {
  onLogin: () => void
  notice?: string
}) {
  const [activeIndex, setActiveIndex] = useState(0)
  const [trackPosition, setTrackPosition] = useState(cards.length)
  const [viewportWidth, setViewportWidth] = useState(0)
  const [paused, setPaused] = useState(false)
  const [transitionEnabled, setTransitionEnabled] = useState(true)
  const animationFrame = useRef<number | null>(null)
  const viewportRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    const observer = new ResizeObserver(([entry]) => setViewportWidth(entry.contentRect.width))
    observer.observe(viewport)
    return () => observer.disconnect()
  }, [])

  useEffect(() => () => {
    if (animationFrame.current !== null) window.cancelAnimationFrame(animationFrame.current)
  }, [])

  const carouselItems = [
    ...cards,
    ...cards,
    ...cards,
  ]
  const cardWidth = viewportWidth < 700
    ? viewportWidth * 0.72
    : Math.min(420, viewportWidth * 0.5)

  const moveBy = useCallback((direction: -1 | 1) => {
    setActiveIndex((current) => (current + direction + cards.length) % cards.length)
    setTrackPosition((current) => current + direction)
  }, [])

  useEffect(() => {
    if (paused) return
    const timer = window.setInterval(() => moveBy(1), 3000)
    return () => window.clearInterval(timer)
  }, [moveBy, paused])

  const handleTransitionEnd = (event: TransitionEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget || event.propertyName !== 'transform') return
    if (trackPosition >= cards.length && trackPosition < cards.length * 2) return
    setTransitionEnabled(false)
    setTrackPosition((current) => current >= cards.length * 2 ? current - cards.length : current + cards.length)
    animationFrame.current = window.requestAnimationFrame(() => {
      animationFrame.current = window.requestAnimationFrame(() => {
        setTransitionEnabled(true)
        animationFrame.current = null
      })
    })
  }

  return (
    <main className="app-shell welcome-shell">
      <header className="welcome-header">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true"><span className="welcome-brand-mark">O</span></div>
          <div><b>동백전</b><span>부산시민플랫폼</span></div>
        </div>
        <button className="welcome-login-link" onClick={onLogin}>로그인</button>
      </header>

      <section className="welcome-hero welcome-news-hero" aria-labelledby="welcome-news-title">
        <div className="welcome-section-heading">
          <div>
            <span>ONEPASS 소식</span>
            <time dateTime="2026-11-02">2026.11.02</time>
            <h1 id="welcome-news-title">신규가입자에게 카드를!</h1>
          </div>
          <CreditCard size={22} aria-hidden="true" />
        </div>
        <p className="welcome-news-description">신규 가입자라면 아래 네 가지 카드 중 하나를 골라보세요!</p>
        <div
          className="welcome-carousel"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          onFocusCapture={() => setPaused(true)}
          onBlurCapture={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setPaused(false)
          }}
          role="region"
          aria-roledescription="carousel"
          aria-label="OnePass 카드 이미지"
        >
          <div className="welcome-carousel-viewport" ref={viewportRef}>
            <div
              className={`welcome-carousel-track ${transitionEnabled ? '' : 'no-transition'}`}
              style={{
                transform: `translateX(${viewportWidth / 2 - (trackPosition + 0.5) * cardWidth}px)`,
              }}
              onTransitionEnd={handleTransitionEnd}
            >
              {carouselItems.map((card, cardIndex) => (
                <article
                  className={`welcome-carousel-card ${cardIndex % cards.length === activeIndex ? 'active' : ''}`}
                  key={`${card.variant}-${cardIndex}`}
                  style={{ flex: `0 0 ${cardWidth}px` }}
                  role="group"
                  aria-roledescription="slide"
                  aria-label={`${card.title}`}
                  aria-hidden={Math.abs(cardIndex - trackPosition) > 1}
                >
                  <DongiImage variant={card.variant} alt={card.imageAlt} className="welcome-carousel-image" priority={cardIndex === cards.length} />
                  <span>{card.title}</span>
                </article>
              ))}
            </div>
          </div>
          <div className="welcome-carousel-controls">
            <span>{`${activeIndex + 1} / ${cards.length}`}</span>
            <button type="button" aria-label="이전 카드" onClick={() => moveBy(-1)}><ArrowLeft size={16} /></button>
            <button type="button" aria-label="다음 카드" onClick={() => moveBy(1)}><ArrowRight size={16} /></button>
          </div>
        </div>
      </section>
      {notice && <p className="welcome-notice" role="status">{notice}</p>}

      <p className="welcome-footnote">카드 등록 및 개인별 기능은 로그인 후 이용할 수 있습니다.</p>
    </main>
  )
}
