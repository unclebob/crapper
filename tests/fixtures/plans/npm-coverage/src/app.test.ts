import assert from 'node:assert'
import { test } from 'node:test'
import { plan } from './app.ts'

test('plan', () => {
  assert.equal(plan(true), 1)
  assert.equal(plan(false), 0)
})
