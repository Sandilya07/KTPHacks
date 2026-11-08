import { useEffect, useRef } from 'react'
import { COLORS, CURSOR, FINISH, FRAGMENT_SHADER, SHAPE, SURFACE, TIME_SCALE, TRANSFORM, VERTEX_SHADER } from './shader'

function compile(gl: WebGLRenderingContext, type: number, source: string) {
  const shader = gl.createShader(type)!
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) || 'Shader failed to compile')
  return shader
}

/** Full-bleed animated "Mesh drift" shader (plain WebGL1, one fullscreen triangle). Sits behind page content. */
interface Props {
  className?: string
  /** Render-resolution multiplier (1 = full). The field is soft, so a permanent backdrop can run at ~0.4. */
  resolution?: number
  /** Frame-rate cap. */
  fps?: number
}

export default function ShaderBackground({ className = '', resolution = 1, fps = 60 }: Props) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const gl = canvas.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power' })
    if (!gl) return // the CSS background on the parent remains as the fallback

    let program: WebGLProgram
    try {
      program = gl.createProgram()!
      gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX_SHADER))
      gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER))
      gl.linkProgram(program)
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || 'Link failed')
    } catch (error) {
      console.warn('Shader background disabled:', error)
      return
    }
    gl.useProgram(program)

    const buffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    const position = gl.getAttribLocation(program, 'a_pos')
    gl.enableVertexAttribArray(position)
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0)

    const loc = (name: string) => gl.getUniformLocation(program, name)
    const colors = new Float32Array(24)
    COLORS.forEach((color, i) => colors.set(color, i * 3))
    gl.uniform3fv(loc('u_colors'), colors)
    gl.uniform4f(loc('u_shape'), ...SHAPE)
    gl.uniform4f(loc('u_surface'), ...SURFACE)
    gl.uniform4f(loc('u_finish'), ...FINISH)
    gl.uniform4f(loc('u_transform'), ...TRANSFORM)
    gl.uniform4f(loc('u_space'), 0, 0, 0, 0) // cursor is off, so pointer position is unused
    gl.uniform4f(loc('u_cursor'), ...CURSOR)
    const scene = loc('u_scene')

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const started = performance.now()
    let frame = 0
    let width = 0
    let height = 0

    function resize() {
      const ratio = Math.min(window.devicePixelRatio || 1, 2) * resolution
      const w = Math.max(1, Math.round(canvas!.clientWidth * ratio))
      const h = Math.max(1, Math.round(canvas!.clientHeight * ratio))
      if (w !== width || h !== height) { width = canvas!.width = w; height = canvas!.height = h; gl!.viewport(0, 0, w, h) }
    }
    function draw(now: number) {
      resize()
      const seconds = reduceMotion ? 12 : (now - started) / 1000 // reduced motion: a single still frame
      gl!.uniform4f(scene, width, height, seconds * TIME_SCALE, COLORS.length)
      gl!.drawArrays(gl!.TRIANGLES, 0, 3)
    }
    const minGap = 1000 / fps - 2
    let lastDraw = 0
    function loop(now: number) {
      frame = requestAnimationFrame(loop)
      if (now - lastDraw < minGap) return
      lastDraw = now
      draw(now)
    }
    function start() { if (!frame && !reduceMotion) frame = requestAnimationFrame(loop) }
    function stop() { cancelAnimationFrame(frame); frame = 0 }
    function visibility() { if (document.hidden) stop(); else start() }

    draw(performance.now())
    start()
    document.addEventListener('visibilitychange', visibility)
    const redraw = () => draw(performance.now())
    window.addEventListener('resize', redraw)
    return () => {
      stop()
      document.removeEventListener('visibilitychange', visibility)
      window.removeEventListener('resize', redraw)
      // No loseContext() here: StrictMode re-runs this effect on the same canvas and would get a dead context.
    }
  }, [resolution, fps])

  return <canvas ref={ref} aria-hidden className={`absolute inset-0 h-full w-full ${className}`} />
}
