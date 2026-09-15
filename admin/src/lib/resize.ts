/**
 * 拖拽调整尺寸的公共逻辑（表格列宽、抽屉宽度都用它）
 *
 * 用 Pointer Events 而不是 mouse events：鼠标、触控板、触屏一套代码搞定。
 * 拖拽期间监听挂在 window 上并配合 setPointerCapture，指针移出元素也不会中断。
 */

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export interface ResizeOptions {
  /** 最小尺寸（px） */
  min: number;
  /** 最大尺寸（px），可以传函数以便按窗口大小实时计算 */
  max: number | (() => number);
  /**
   * 拖拽方向：
   *  1 = 手柄在右边（往右拖变大，比如表格列）
   * -1 = 手柄在左边（往左拖变大，比如右侧抽屉）
   */
  sign?: 1 | -1;
  /** 拖拽过程中回调新尺寸 */
  onMove: (size: number) => void;
  /** 拖拽结束（用来落盘保存） */
  onEnd?: () => void;
}

/**
 * 开始一次尺寸拖拽。
 *
 * @param event pointerdown 事件
 * @param base  拖拽前的尺寸，作为增量基准
 */
export function beginResize(
  event: PointerEvent,
  base: number,
  options: ResizeOptions,
): void {
  const startX = event.clientX;
  const sign = options.sign ?? 1;
  const maxOption = options.max;
  const maxOf = (): number =>
    typeof maxOption === "function" ? maxOption() : maxOption;
  const target = event.currentTarget as HTMLElement | null;

  // 别让这次按下变成点击（表格行有 @click 打开详情，抽屉外面有 @click 关闭）
  event.preventDefault();
  event.stopPropagation();

  target?.setPointerCapture?.(event.pointerId);

  const previousUserSelect = document.body.style.userSelect;
  document.body.style.userSelect = "none";

  const handleMove = (moveEvent: PointerEvent) => {
    const delta = (moveEvent.clientX - startX) * sign;
    options.onMove(clamp(base + delta, options.min, maxOf()));
  };

  const finish = () => {
    window.removeEventListener("pointermove", handleMove);
    window.removeEventListener("pointerup", finish);
    window.removeEventListener("pointercancel", finish);
    target?.releasePointerCapture?.(event.pointerId);
    document.body.style.userSelect = previousUserSelect;
    options.onEnd?.();
  };

  window.addEventListener("pointermove", handleMove);
  window.addEventListener("pointerup", finish);
  window.addEventListener("pointercancel", finish);
}

/** 从 localStorage 读一个数字数组（列宽），不合法就返回 null */
export function loadNumberArray(key: string, expectedLength: number): number[] | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      Array.isArray(parsed) &&
      parsed.length === expectedLength &&
      parsed.every((item) => typeof item === "number" && item > 0)
    ) {
      return parsed as number[];
    }
  } catch {
    /* 忽略损坏的本地数据 */
  }
  return null;
}

/** 从 localStorage 读一个数字，不合法返回 null */
export function loadNumber(key: string): number | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const value = Number(raw);
    return Number.isFinite(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

export function saveValue(key: string, value: number | number[]): void {
  try {
    localStorage.setItem(
      key,
      Array.isArray(value) ? JSON.stringify(value) : String(value),
    );
  } catch {
    /* 存不进去也不影响使用 */
  }
}

export function clearValue(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    /* 忽略 */
  }
}
