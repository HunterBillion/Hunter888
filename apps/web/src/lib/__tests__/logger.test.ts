import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { logger } from '../logger'

describe('logger', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  describe('log', () => {
    it('should log messages in development', () => {
      const consoleSpy = vi.spyOn(console, 'log')
      vi.stubEnv('NODE_ENV', 'development')

      logger.log('test message')

      expect(consoleSpy).toHaveBeenCalledWith('test message')
      consoleSpy.mockRestore()
    })

    it('should not log messages in production', () => {
      const consoleSpy = vi.spyOn(console, 'log')
      vi.stubEnv('NODE_ENV', 'production')

      logger.log('test message')

      expect(consoleSpy).not.toHaveBeenCalled()
      consoleSpy.mockRestore()
    })

    it('should handle multiple arguments', () => {
      const consoleSpy = vi.spyOn(console, 'log')
      vi.stubEnv('NODE_ENV', 'development')

      logger.log('msg', { data: 'value' }, 42)

      expect(consoleSpy).toHaveBeenCalledWith('msg', { data: 'value' }, 42)
      consoleSpy.mockRestore()
    })
  })

  describe('warn', () => {
    it('should warn in development', () => {
      const consoleSpy = vi.spyOn(console, 'warn')
      vi.stubEnv('NODE_ENV', 'development')

      logger.warn('warning message')

      expect(consoleSpy).toHaveBeenCalledWith('warning message')
      consoleSpy.mockRestore()
    })

    it('should not warn in production', () => {
      const consoleSpy = vi.spyOn(console, 'warn')
      vi.stubEnv('NODE_ENV', 'production')

      logger.warn('warning message')

      expect(consoleSpy).not.toHaveBeenCalled()
      consoleSpy.mockRestore()
    })
  })

  describe('error', () => {
    it('should error with full details in development', () => {
      const consoleSpy = vi.spyOn(console, 'error')
      vi.stubEnv('NODE_ENV', 'development')

      const error = new Error('test error')
      logger.error(error)

      expect(consoleSpy).toHaveBeenCalledWith(error)
      consoleSpy.mockRestore()
    })

    it('should redact sensitive data in production', () => {
      const consoleSpy = vi.spyOn(console, 'error')
      vi.stubEnv('NODE_ENV', 'production')

      const error = new Error('test error')
      logger.error(error, { sensitive: 'data' })

      expect(consoleSpy).toHaveBeenCalledWith('test error', '[redacted]')
      consoleSpy.mockRestore()
    })

    it('should handle string error messages in production', () => {
      const consoleSpy = vi.spyOn(console, 'error')
      vi.stubEnv('NODE_ENV', 'production')

      logger.error('simple error message')

      expect(consoleSpy).toHaveBeenCalledWith('simple error message')
      consoleSpy.mockRestore()
    })

    it('should redact objects in production but preserve Error messages', () => {
      const consoleSpy = vi.spyOn(console, 'error')
      vi.stubEnv('NODE_ENV', 'production')

      const error = new Error('api failed')
      logger.error('Failed:', error, { userId: 123 })

      expect(consoleSpy).toHaveBeenCalledWith('Failed:', 'api failed', '[redacted]')
      consoleSpy.mockRestore()
    })
  })
})
