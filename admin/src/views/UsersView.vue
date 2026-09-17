<script setup lang="ts">
/** 用户管理：列表（可拖拽列宽）+ 行内操作 + 只读详情抽屉 */
import { computed, onMounted, ref } from "vue";
import { Columns3, Loader2, RefreshCw, Search, Users } from "@lucide/vue";

import UserActions from "../components/UserActions.vue";
import UserDetail from "../components/UserDetail.vue";
import { ApiError, fetchUsers } from "../lib/api";
import { formatDate, formatTokens } from "../lib/format";
import { useColumns, type ColumnDef } from "../lib/useColumns";
import type { AdminUserRow } from "../types";

const props = defineProps<{ adminName: string }>();
const emit = defineEmits<{
  (e: "notify", payload: { type: "ok" | "error"; text: string }): void;
  (e: "auth-expired"): void;
}>();

const COLUMNS: ColumnDef[] = [
  { key: "id", label: "ID", width: 64, min: 48, align: "left" },
  { key: "user", label: "用户", width: 200, min: 130, align: "left" },
  { key: "role", label: "角色", width: 96, min: 76, align: "left" },
  { key: "threads", label: "会话", width: 80, min: 64, align: "right" },
  { key: "sessions", label: "设备", width: 80, min: 64, align: "right" },
  { key: "usage", label: "本周用量", width: 150, min: 110, align: "right" },
  { key: "quota", label: "剩余额度", width: 120, min: 90, align: "right" },
  { key: "created", label: "注册时间", width: 120, min: 100, align: "left" },
  { key: "actions", label: "操作", width: 170, min: 150, align: "right" },
];

const COLUMN_STORAGE_KEY = "chef_admin_cols_users_v2";

const {
  widths: colWidths,
  boxRef: scrollBoxRef,
  totalWidth: tableWidth,
  startResize: startColumnResize,
  resetOne: resetColumn,
  resetAll: resetAllColumns,
} = useColumns(COLUMN_STORAGE_KEY, COLUMNS);

const users = ref<AdminUserRow[]>([]);
const total = ref(0);
const page = ref(1);
const size = ref(20);
const query = ref("");
const searchInput = ref("");
const loading = ref(false);
const listError = ref("");

const selectedId = ref<number | null>(null);

const pageCount = computed(() => Math.max(Math.ceil(total.value / size.value), 1));

const rangeText = computed(() => {
  if (total.value === 0) return "共 0 个用户";
  const start = (page.value - 1) * size.value + 1;
  const end = Math.min(page.value * size.value, total.value);
  return `第 ${start}-${end} 条 / 共 ${total.value} 个用户`;
});

async function refresh() {
  loading.value = true;
  listError.value = "";
  try {
    const data = await fetchUsers({ q: query.value, page: page.value, size: size.value });
    users.value = data.items;
    total.value = data.total;
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
      emit("auth-expired");
      return;
    }
    listError.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);

function search() {
  query.value = searchInput.value.trim();
  page.value = 1;
  refresh();
}

function goPage(next: number) {
  if (next < 1 || next > pageCount.value) return;
  page.value = next;
  refresh();
}
</script>

<template>
  <div class="flex-1 min-h-0 flex flex-col">
    <!-- 工具栏 -->
    <div class="shrink-0 px-5 py-3 flex items-center gap-2 flex-wrap">
      <div class="relative">
        <Search :size="14" class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          v-model="searchInput"
          type="text"
          placeholder="按用户名或昵称搜索"
          class="pl-8 pr-3 py-2 w-56 text-sm rounded-xl border border-slate-200 bg-white focus:border-slate-400 outline-none transition"
          @keyup.enter="search"
        />
      </div>
      <button
        class="px-3 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-sm transition"
        @click="search"
      >
        搜索
      </button>
      <button
        v-if="query"
        class="px-3 py-2 rounded-xl border border-slate-200 bg-white hover:border-slate-400 text-sm text-slate-600 transition"
        @click="searchInput = ''; search()"
      >
        清空
      </button>
      <button
        class="ml-auto flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200 bg-white hover:border-slate-400 text-sm text-slate-600 transition"
        :disabled="loading"
        @click="refresh"
      >
        <RefreshCw :size="14" :class="loading ? 'animate-spin' : ''" />
        <span>刷新</span>
      </button>
      <button
        class="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-slate-200 bg-white hover:border-slate-400 text-sm text-slate-600 transition"
        title="把各列宽度恢复成默认并铺满整行"
        @click="resetAllColumns"
      >
        <Columns3 :size="14" />
        <span>重置列宽</span>
      </button>
    </div>

    <!-- 列表 -->
    <div class="flex-1 min-h-0 px-5 pb-4">
      <div class="h-full bg-white rounded-2xl border border-slate-200 overflow-hidden flex flex-col">
        <div
          v-if="listError"
          class="px-4 py-2 text-xs text-red-500 bg-red-50 border-b border-red-100"
        >
          {{ listError }}
        </div>

        <div ref="scrollBoxRef" class="flex-1 overflow-auto">
          <table
            class="w-full text-sm"
            :style="{ tableLayout: 'fixed', width: '100%', minWidth: `${tableWidth}px` }"
          >
            <colgroup>
              <col
                v-for="(column, index) in COLUMNS"
                :key="column.key"
                :style="{ width: `${colWidths[index]}px` }"
              />
              <!-- 占位列：吃掉剩余宽度，这样真实列渲染出来就是设定的像素值，
                   拖某一列时其它列不会跟着变（否则浏览器会按比例缩放） -->
              <col />
            </colgroup>
            <thead class="bg-slate-50 text-slate-500 text-xs sticky top-0 z-10">
              <tr>
                <th
                  v-for="(column, index) in COLUMNS"
                  :key="column.key"
                  class="relative font-medium px-4 py-2.5 select-none"
                  :class="column.align === 'right' ? 'text-right' : 'text-left'"
                >
                  <span class="truncate">{{ column.label }}</span>
                  <!-- 拖拽手柄：视觉上是一条分隔线，命中区域放宽到 8px 更好抓 -->
                  <span
                    class="group/handle absolute right-0 top-0 h-full w-2 cursor-col-resize"
                    :title="`拖拽调整「${column.label}」列宽，双击恢复默认`"
                    @pointerdown="startColumnResize($event, index)"
                    @dblclick="resetColumn(index)"
                  >
                    <span
                      class="absolute inset-y-0 right-0 w-px bg-slate-200 group-hover/handle:bg-slate-400 transition-colors"
                    />
                  </span>
                </th>
                <th class="font-medium" aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="user in users"
                :key="user.id"
                class="border-t border-slate-100 hover:bg-slate-50 cursor-pointer transition"
                :class="selectedId === user.id ? 'bg-slate-50' : ''"
                @click="selectedId = user.id"
              >
                <td class="px-4 py-2.5 text-slate-400">{{ user.id }}</td>
                <td class="px-4 py-2.5">
                  <div class="font-medium text-slate-800">
                    {{ user.display_name || user.username }}
                  </div>
                  <div class="text-[11px] text-slate-400">{{ user.username }}</div>
                </td>
                <td class="px-4 py-2.5">
                  <span
                    class="text-[11px] px-2 py-0.5 rounded-full"
                    :class="
                      user.is_admin ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-500'
                    "
                  >
                    {{ user.is_admin ? "管理员" : "用户" }}
                  </span>
                </td>
                <td class="px-4 py-2.5 text-right text-slate-600">{{ user.threads }}</td>
                <td class="px-4 py-2.5 text-right text-slate-600">{{ user.sessions }}</td>
                <td class="px-4 py-2.5 text-right text-slate-600">
                  {{ formatTokens(user.used_this_week) }}
                  <span class="text-[11px] text-slate-400">/ {{ user.requests_this_week }} 次</span>
                </td>
                <td class="px-4 py-2.5 text-right">
                  <span v-if="user.effective_quota <= 0" class="text-slate-400">不限</span>
                  <span
                    v-else
                    :class="(user.remaining ?? 0) <= 0 ? 'text-red-600' : 'text-slate-600'"
                  >
                    {{ formatTokens(user.remaining ?? 0) }}
                  </span>
                </td>
                <td class="px-4 py-2.5 text-slate-500 text-xs">
                  {{ formatDate(user.created_at) }}
                </td>
                <td class="px-2 py-1.5">
                  <!-- 所有对用户的操作都在这里；自己的账号会禁用敏感操作 -->
                  <UserActions
                    :user="user"
                    :self="user.username === props.adminName"
                    @changed="refresh"
                    @notify="(payload) => emit('notify', payload)"
                  />
                </td>
                <td aria-hidden="true" />
              </tr>
              <tr v-if="!loading && users.length === 0">
                <td :colspan="COLUMNS.length + 1" class="px-4 py-10 text-center text-slate-400">
                  <Users :size="22" class="mx-auto mb-2 opacity-50" />
                  {{ query ? "没有匹配的用户" : "还没有用户" }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div
          class="shrink-0 border-t border-slate-100 px-4 py-2.5 flex items-center gap-3 text-xs text-slate-500"
        >
          <Loader2 v-if="loading" :size="14" class="animate-spin" />
          <span>{{ rangeText }}</span>
          <div class="ml-auto flex items-center gap-2">
            <button
              class="px-2.5 py-1 rounded-lg border border-slate-200 hover:border-slate-400 disabled:opacity-40 transition"
              :disabled="page <= 1"
              @click="goPage(page - 1)"
            >
              上一页
            </button>
            <span>{{ page }} / {{ pageCount }}</span>
            <button
              class="px-2.5 py-1 rounded-lg border border-slate-200 hover:border-slate-400 disabled:opacity-40 transition"
              :disabled="page >= pageCount"
              @click="goPage(page + 1)"
            >
              下一页
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 用户详情抽屉（只读） -->
    <UserDetail v-if="selectedId !== null" :user-id="selectedId" @close="selectedId = null" />
  </div>
</template>
