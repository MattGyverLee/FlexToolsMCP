# FlexTools MCP Background

The story of how and why FlexTools MCP was created.

## The Dream

Since I started working with AI, I dreamed of having an AI tool that could assist with or write "proper" FLExTools modules. The challenge was that the "agent" needed to deeply understand the FLEx Model, FLExTools preferences, which FlexTools functions existed, and when to fall back to the FieldWorks API (flexlibs). This was too much data to be held in memory for AI work, or for most humans.

## Early Attempts (Summer 2025)

Since summer of 2025, I've tried to build a Chipp AI agent for this task by giving it existing documentation and some code, and the results were dismal. It would call functions that didn't exist and required significant handholding to massage the drafts into something workable.

## FlexLibs 2.0 (Christmas 2025)

I realized that one barrier to progress was enabling FLExTools (flexlibs) to access and edit the WHOLE FLEx database (not having to learn and switch between the FlexTools and FLEx backends). Christmas of 2025, I set Claude Code on the task of a COMPLETE rewrite of FlexLibs that I'm calling FlexLibs 2.0.

Instead of the ~70 functions currently supported in FlexLibs stable, FlexLibs 2.0 provides nearly 1,400 functions covering full CRUD operations for the Lexicon, Grammar, Texts, Words, Lists, Scripture, and Notebook domains.

A byproduct of the process was an early abstracted annotated JSON representation of LibLCM ([flex-api-enhanced.json](../index/liblcm/flex-api-enhanced.json)).

## The MCP Insight (February 4th, 2025)

In February 4th conversations with Larry Hayashi and Jason Naylor, I realized that instead of building an AI Agent with all of the skills (running and looping in-memory, which is very expensive and inefficient), what was needed was an MCP server (an external brain) that could quickly and efficiently look up the needed functions and structure that the AI could piece together.

## Building the MCP (February 5th, 2025)

The evening of February 5th, I started by enriching the shallow annotated code indexes of FlexLib and LibLCM that I had, and then built a new index of FlexLibs 2.0 (which already links the Python and C# functions explicitly). The results are:

- [flexlibs_api.json](../index/flexlibs/flexlibs_api.json) - FlexLibs stable (~71 methods)
- [flexlibs2_api.json](../index/flexlibs/flexlibs2_api.json) - FlexLibs 2.0 (~1,400 methods)
- [liblcm_api.json](../index/liblcm/liblcm_api.json) - LibLCM C# API

The MCP server was built with a host of tools to enable AI assistants to query those abstractions based on natural language input.

## The Breakthrough

The breakthrough came when Claude Code (using the MCP) could generate at will:
- **Legacy FlexTool Modules** that prefer FlexLibs stable calls with LibLCM fallback
- **Modern FlexTool Modules** that use entirely FlexLibs 2.0 calls
- **Pure LibLCM Modules** that skip FlexLibs entirely and make direct LibLCM calls

## Beyond Code Generation

Beyond FlexTools module generation, the MCP can alternately run code directly on the database, enabling natural language editing of ANY FLEx data without writing a full module.

My goal was to successfully write FLExTool modules, but I accidentally created what Doug hoped to see: a scary-powerful natural-language interface to interact with FieldWorks data.

## Timeline Summary

| Date | Milestone |
|------|-----------|
| Summer 2025 | First attempts with Chipp AI agent |
| Christmas 2025 | FlexLibs 2.0 rewrite begins |
| February 4, 2025 | MCP architecture insight from Larry & Jason |
| February 5, 2025 | MCP server development begins |
| February 2025 | First successful module generation |

## Key People

- **Matthew Lee** - Project developer
- **Larry Hayashi** - MCP architecture discussions
- **Jason Naylor** - MCP architecture discussions
- **Doug** - Vision for natural language FLEx interface
- **Craig** - Original FLExTools and FlexLibs developer
