/// <reference types="vite/client" />

/*
 * 这里**故意不写** `declare module '*.vue'` 的兜底声明。
 *
 * 那种写法长这样：
 *     declare module '*.vue' {
 *       const c: DefineComponent<{}, {}, any>
 *       export default c
 *     }
 * 它会让**每一个** .vue 导入都退化成 `DefineComponent<{},{},any>`——
 * 也就是 props 全变 `any`、模板里传错 prop 不再报错。
 * 那正好把「新组件有类型」这个 D3 的全部收益抵消掉了。
 *
 * 该声明只对**纯 tsc**（不认识 .vue）的项目有意义。本项目用 vue-tsc，
 * 它原生解析 .vue（含 `<script setup>` 的宏与模板类型推断），不需要也**不应该**加这层兜底。
 */
