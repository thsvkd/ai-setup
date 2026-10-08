import { describe, expect, mock, test } from 'claude-code/testing'
import { format, touchesCache } from './register'

const T0 = 1_000_000_000

describe('format', () => {
  test('캐시를 쓴 적이 없으면 아무것도 보이지 않는다', () => {
    expect(format(undefined, T0)).toBe(undefined)
  })
  test('1분 이상은 분, 미만은 초, 지나면 cold', () => {
    expect(format(T0 + 57 * 60_000 + 5_000, T0)).toBe('cache:57m')
    expect(format(T0 + 45_000, T0)).toBe('cache:45s')
    expect(format(T0, T0)).toBe('cache:cold')
    expect(format(0, T0)).toBe('cache:cold')
  })
})

describe('touchesCache', () => {
  test('캐시를 읽거나 쓴 응답만 TTL 을 갱신한다', () => {
    expect(touchesCache({ cache_read_input_tokens: 10, cache_creation_input_tokens: 0 })).toBe(true)
    expect(touchesCache({ cache_read_input_tokens: 0, cache_creation_input_tokens: 5 })).toBe(true)
    expect(touchesCache({ cache_read_input_tokens: 0, cache_creation_input_tokens: 0 })).toBe(false)
    expect(touchesCache(null)).toBe(false)
  })
})

function stepResult(e: { turnId: string; index: number }, read: number) {
  return {
    turnId: e.turnId, index: e.index, answer: '', toolUses: [], stopReason: 'end_turn' as const,
    usage: { input_tokens: 1, output_tokens: 1, cache_read_input_tokens: read, cache_creation_input_tokens: 0, model: 'm' },
  }
}

async function runStep($: any, input: object) {
  const stream = $.turn.step(input)
  for await (const _ of stream) { /* 응답 조각은 보지 않는다 */ }
  return stream.result
}

test('메인 요청이 캐시를 읽으면 TTL 이 흐르고, 지나면 cold 가 된다', { options: { ttl: '5m' } }, async ($, on) => {
  const clock = mock.clock(on, { now: T0 })
  const seen: (string | undefined)[] = []
  on('ui.status', async (_$, e) => { seen.push(e.text); return { value: undefined } })
  on('turn.step', async function* (_$, e) { return stepResult(e, 100) })
  on('session.start', async (_$, e) => e as never)

  await $.session.start({ cwd: '/work' } as never)
  await runStep($, { turnId: 't', index: 0, model: 'm', messageCount: 1 })
  expect(seen.at(-1)).toBe('cache:5m')

  await clock.advance(4 * 60_000 + 30_000)
  expect(seen.at(-1)).toBe('cache:30s')

  await clock.advance(31_000)
  expect(seen.at(-1)).toBe('cache:cold')
})

test('서브에이전트 요청과 캐시를 건드리지 않은 요청은 무시한다', async ($, on) => {
  mock.clock(on, { now: T0 })
  const seen: (string | undefined)[] = []
  on('ui.status', async (_$, e) => { seen.push(e.text); return { value: undefined } })
  on('turn.step', async function* (_$, e) { return stepResult(e, e.agentId ? 100 : 0) })

  await runStep($, { turnId: 't', index: 0, model: 'm', messageCount: 1, agentId: 'a1' })
  await runStep($, { turnId: 't', index: 1, model: 'm', messageCount: 1 })
  expect(seen).toEqual([])
})

test('모델을 바꾸면 cold 가 되고, 엔진이 알려 준 TTL 을 쓴다', { options: { ttl: '1h' } }, async ($, on) => {
  mock.clock(on, { now: T0 })
  const seen: (string | undefined)[] = []
  on('ui.status', async (_$, e) => { seen.push(e.text); return { value: undefined } })
  on('turn.step', async function* (_$, e) { return stepResult(e, 100) })
  on('classic.PostModelSwitch', async () => ({}) as never)

  await runStep($, { turnId: 't', index: 0, model: 'm', messageCount: 1 })
  expect(seen.at(-1)).toBe('cache:60m')

  await $.classic.PostModelSwitch({
    from_model: 'a', to_model: 'b', requested_model: null, source: 'command',
    context_tokens: 1, prompt_cache_warm: true, cache_ttl: '5m', estimated_cache_write_usd: 0, pricing: 'catalog',
  } as never)
  expect(seen.at(-1)).toBe('cache:cold')

  await runStep($, { turnId: 't', index: 1, model: 'b', messageCount: 2 })
  expect(seen.at(-1)).toBe('cache:5m')
})

test('session.start 없이 로드돼도(reload) 첫 요청부터 카운트다운이 흐른다', { options: { ttl: '5m' } }, async ($, on) => {
  const clock = mock.clock(on, { now: T0 })
  const seen: (string | undefined)[] = []
  on('ui.status', async (_$, e) => { seen.push(e.text); return { value: undefined } })
  on('turn.step', async function* (_$, e) { return stepResult(e, 100) })

  await runStep($, { turnId: 't', index: 0, model: 'm', messageCount: 1 })
  // 예전 글자를 먼저 지우고 새 값을 그린다
  expect(seen).toEqual([undefined, 'cache:5m'])
  await clock.advance(4 * 60_000 + 30_000)
  expect(seen.at(-1)).toBe('cache:30s')
})
