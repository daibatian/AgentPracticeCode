<script setup lang="ts">
/** 通用弹窗外壳：遮罩 + 居中卡片 + 标题栏 + 可选底栏 */
import { X } from "@lucide/vue";

defineProps<{ title: string; maxWidth?: string }>();
const emit = defineEmits<{ (e: "close"): void }>();
</script>

<template>
  <!-- Teleport 到 body：弹窗挂在表格单元格里时，点击会冒泡到整行（行有点击事件），
       挪出去之后就不会误触发行操作了 -->
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-center justify-center p-4" @click.self="emit('close')">
      <div class="absolute inset-0 bg-slate-900/30" @click="emit('close')" />
      <div
        class="relative w-full bg-white rounded-2xl shadow-2xl flex flex-col"
        :style="{ maxWidth: maxWidth ?? '26rem' }"
      >
        <header class="px-5 py-3.5 border-b border-slate-200 flex items-center gap-3">
          <h3 class="flex-1 text-sm font-semibold text-slate-800">{{ title }}</h3>
          <button
            class="p-1 text-slate-400 hover:text-slate-600"
            aria-label="关闭"
            @click="emit('close')"
          >
            <X :size="16" />
          </button>
        </header>

        <div class="px-5 py-4">
          <slot />
        </div>

        <footer
          v-if="$slots.footer"
          class="px-5 py-3 border-t border-slate-200 flex justify-end gap-2"
        >
          <slot name="footer" />
        </footer>
      </div>
    </div>
  </Teleport>
</template>
