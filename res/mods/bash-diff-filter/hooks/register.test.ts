import { describe, expect, test } from 'claude-code/testing'
import { filterOutput } from './register'

const HUD = 'C:\\work\\proj\\.omc\\state\\hud-stdin-cache.json'
const HUD_SESSION = '/work/proj/.omc/state/sessions/abc-123/hud-stdin-cache.json'
const SRC = '/work/proj/src/app.ts'
const hunk = { oldStart: 1, oldLines: 1, newStart: 1, newLines: 1, lines: ['-a', '+b'] }

function bash(files: string[], moreFiles = 0) {
  return {
    stdout: 'ok', stderr: '', interrupted: false,
    bashEditDiff: { files: files.map((filePath) => ({ filePath, hunks: [hunk] })), moreFiles, changedFiles: files },
  }
}

describe('filterOutput', () => {
  test('HUD 캐시만 빼고 다른 파일은 남긴다', () => {
    const out = filterOutput(bash([HUD, SRC]))
    expect(out.bashEditDiff?.files.map((f) => f.filePath)).toEqual([SRC])
    expect(out.bashEditDiff?.changedFiles).toEqual([SRC])
    expect(out.stdout).toBe('ok')
  })

  test('세션별 경로도 뺀다', () => {
    expect(filterOutput(bash([HUD_SESSION, SRC])).bashEditDiff?.files.length).toBe(1)
  })

  test('HUD 캐시뿐이면 bashEditDiff 를 통째로 지운다', () => {
    expect('bashEditDiff' in filterOutput(bash([HUD]))).toBe(false)
  })

  test('잘린 파일이 더 있으면 빈 목록이어도 bashEditDiff 를 남긴다', () => {
    const out = filterOutput(bash([HUD], 3))
    expect(out.bashEditDiff?.files).toEqual([])
    expect(out.bashEditDiff?.moreFiles).toBe(3)
  })

  test('목록에서 잘린 HUD 캐시는 +N more 숫자에서 뺀다', () => {
    const input = bash([SRC], 2)
    input.bashEditDiff.changedFiles = [SRC, HUD, '/work/proj/other.ts']
    const out = filterOutput(input)
    expect(out.bashEditDiff?.files.map((f) => f.filePath)).toEqual([SRC])
    expect(out.bashEditDiff?.moreFiles).toBe(1)
    expect(out.bashEditDiff?.changedFiles).toEqual([SRC, '/work/proj/other.ts'])
  })

  test('걸러낼 게 없으면 같은 객체를 돌려준다', () => {
    const input = bash([SRC])
    expect(filterOutput(input)).toBe(input)
    const plain = { stdout: '', stderr: '', interrupted: false }
    expect(filterOutput(plain)).toBe(plain)
  })

  test('이름만 같은 다른 위치의 파일은 남긴다', () => {
    const other = '/work/proj/docs/hud-stdin-cache.json'
    expect(filterOutput(bash([other])).bashEditDiff?.files.length).toBe(1)
  })
})

for (const component of ['ToolResult', 'ToolUse'] as const) {
  test(`${component}: Bash 결과는 걸러서 엔진에 넘긴다`, async ($, on) => {
    let seen: unknown
    on('ui.render', { component }, async (_$, e) => {
      seen = e.props.output
      return { type: 'Text' as const }
    })
    const base = { tool_use_id: 't1', tool: 'Bash', output: bash([HUD, SRC]), isErrored: false }
    const props = component === 'ToolUse'
      ? { ...base, input: { command: 'ls' }, isRunning: false, isInterrupted: false }
      : base
    await $.ui.render({ surface: 'terminal', component, requestId: 't1', props } as never)
    expect((seen as ReturnType<typeof bash>).bashEditDiff?.files.map((f) => f.filePath)).toEqual([SRC])
  })

  test(`${component}: Bash 가 아닌 도구는 그대로 넘긴다`, async ($, on) => {
    let seen: unknown
    on('ui.render', { component }, async (_$, e) => {
      seen = e.props.output
      return { type: 'Text' as const }
    })
    const output = bash([HUD])
    const base = { tool_use_id: 't2', tool: 'Read', output, isErrored: false }
    const props = component === 'ToolUse'
      ? { ...base, input: {}, isRunning: false, isInterrupted: false }
      : base
    await $.ui.render({ surface: 'terminal', component, requestId: 't2', props } as never)
    expect(seen).toEqual(output)
  })
}
