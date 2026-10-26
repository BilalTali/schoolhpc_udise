import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => cleanup())

// React Router builds a Request for every navigation. Node's Request rejects jsdom's AbortSignal
// ("Expected signal to be an instance of AbortSignal"), so tests drop the signal. Browsers are unaffected.
const NodeRequest = globalThis.Request
globalThis.Request = class extends NodeRequest {
  constructor(input: RequestInfo | URL, init: RequestInit = {}) {
    const { signal: _signal, ...rest } = init
    void _signal
    super(input, rest)
  }
} as typeof Request
