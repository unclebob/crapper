import { expect, test } from 'vitest'
import { plan } from './book'

test('plan', () => {
  expect(plan(true)).toBe(1)
  expect(plan(false)).toBe(0)
})
