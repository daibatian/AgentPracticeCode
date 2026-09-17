/**
 * 表格列宽的公共逻辑（用户表、日志表共用）
 *
 * 默认"自动铺满"：按容器可用宽度把默认比例等比放大，右侧不留白；
 * 一旦用户拖过某一列就切到"手动"：宽度固定成他拖的样子，只记在本地。
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";

import { beginResize, clearValue, loadNumberArray, saveValue } from "./resize";

export interface ColumnDef {
  key: string;
  label: string;
  /** 默认宽度（自动模式下作为比例基准） */
  width: number;
  /** 拖拽时的最小宽度 */
  min: number;
  align?: "left" | "right";
}

export function useColumns(storageKey: string, columns: readonly ColumnDef[]) {
  const defaults = columns.map((column) => column.width);

  const saved = loadNumberArray(storageKey, columns.length);
  const manual = ref(saved !== null);
  const widths = ref<number[]>(saved ?? [...defaults]);

  /** 表格的滚动容器：用来量可用宽度 */
  const boxRef = ref<HTMLElement | null>(null);
  let observer: ResizeObserver | null = null;

  const totalWidth = computed(() =>
    widths.value.reduce((total, width) => total + width, 0),
  );

  function fit() {
    const box = boxRef.value;
    if (!box || manual.value) return;

    const available = box.clientWidth;
    if (available < 200) return;

    const base = defaults.reduce((total, width) => total + width, 0);
    const scale = available / base;
    widths.value = columns.map((column) =>
      Math.max(Math.round(column.width * scale), column.min),
    );
  }

  // 表格往往是异步渲染出来的（登录后、切页签后），所以必须监听 ref：
  // 容器一出现就铺满，并挂上 ResizeObserver 应对窗口尺寸变化
  watch(boxRef, (box) => {
    observer?.disconnect();
    observer = null;
    if (!box) return;

    nextTick(fit);

    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => fit());
      observer.observe(box);
    }
  });

  onBeforeUnmount(() => observer?.disconnect());

  function startResize(event: PointerEvent, index: number) {
    manual.value = true;
    beginResize(event, widths.value[index], {
      min: columns[index].min,
      max: 460,
      onMove: (size) => {
        const next = [...widths.value];
        next[index] = size;
        widths.value = next;
      },
      onEnd: () => saveValue(storageKey, widths.value),
    });
  }

  /** 双击手柄：这一列恢复默认宽度，其余列保持不动 */
  function resetOne(index: number) {
    manual.value = true;
    const next = [...widths.value];
    next[index] = columns[index].width;
    widths.value = next;
    saveValue(storageKey, next);
  }

  /** 工具栏按钮：回到自动铺满 */
  function resetAll() {
    manual.value = false;
    clearValue(storageKey);
    fit();
  }

  return { widths, boxRef, totalWidth, startResize, resetOne, resetAll };
}
