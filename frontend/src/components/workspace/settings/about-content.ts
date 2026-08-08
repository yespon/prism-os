/**
 * About PrismOS markdown content. Inlined to avoid raw-loader dependency
 * (Turbopack cannot resolve raw-loader for .md imports).
 */
export const aboutMarkdown = `# [About PrismOS](https://github.com/yespon/prism-os)

> **From Open Source, Back to Open Source**

PrismOS is a governed Agent operating system for enterprise teams. It provides **multi-tenant workspaces**, **RBAC**, **Skills**, **MCP configuration**, **sandboxed execution**, **artifacts**, and an extensible runtime foundation.

This alpha continues to use the [DeerFlow](https://github.com/bytedance/deer-flow) and [LangGraph](https://github.com/langchain-ai/langgraph) execution stack. Policy, workflow lifecycle, evaluation, connector federation, and runtime independence remain roadmap work rather than completed platform guarantees.

---

## 🚀 Core Features

* **Skills & Tools**: Configure reusable skills and tools for governed workspace execution.
* **Sub-Agents**: Sub-Agents help the main agent to do the tasks that are too complex to be done by the main agent.
* **Sandbox & File System**: Safely execute code and manipulate files in the sandbox.
* **Context Engineering**: Isolated sub-agent context, summarization to keep the context window sharp.
* **Long-Term Memory**: Keep recording the user's profile, top of mind, and conversation history.

---

## 🌟 GitHub Repository

Explore PrismOS on GitHub: [github.com/yespon/prism-os](https://github.com/yespon/prism-os)

## 🌐 Official Website

The project homepage is [github.com/yespon/prism-os](https://github.com/yespon/prism-os).

## 📧 Support

For questions and support, please open an issue in the project repository.

---

## 📜 License

PrismOS is distributed under the **MIT License**. See the repository license and upstream notices for applicable attribution requirements.

---

## 🙌 Acknowledgments

We extend our gratitude to the open source projects and contributors who make PrismOS possible. PrismOS preserves the required DeerFlow and LangGraph attribution; it is not a claim that the upstream runtime was authored here.

### Core Frameworks
- **[LangChain](https://github.com/langchain-ai/langchain)**: A phenomenal framework that powers our LLM interactions and chains.
- **[LangGraph](https://github.com/langchain-ai/langgraph)**: Enabling sophisticated multi-agent orchestration.
- **[Next.js](https://nextjs.org/)**: A cutting-edge framework for building web applications.

### UI Libraries
- **[Shadcn](https://ui.shadcn.com/)**: Minimalistic components that power our UI.
- **[SToneX](https://github.com/stonexer)**: For his invaluable contribution to token-by-token visual effects.

These projects form part of the current PrismOS runtime and UI foundation.

### Special Thanks
Please see the repository history and upstream project acknowledgements for contributors to the inherited codebase.
`;
