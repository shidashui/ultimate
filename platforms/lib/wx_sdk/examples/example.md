# sendText 和 sendMedia 发送流程文档

## 概述

本文档描述 OpenClaw 微信插件中消息发送的核心流程，包括文本消息 (`sendText`) 和媒体文件 (`sendMedia`) 的发送机制。

## 发送入口

### 入口位置

```typescript
// src/channel.ts
export const weixinPlugin: ChannelPlugin<ResolvedWeixinAccount> = {
  // ...
  outbound: {
    deliveryMode: "direct",
    textChunkLimit: 4000,
    sendText: async (ctx) => { /* 文本发送 */ },
    sendMedia: async (ctx) => { /* 媒体发送 */ },
  },
};
```

### 调用链路

```
┌─────────────────────────────────────────────────────────────────┐
│                    OpenClaw Gateway                             │
│                     (发送请求入口)                               │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                     channel.ts                                   │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │   sendText()    │    │   sendMedia()   │                     │
│  └────────┬────────┘    └────────┬────────┘                     │
│           │                      │                              │
│           ▼                      ▼                              │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │ sendMessageWeixin│   │sendWeixinMediaFile                   │
│  └─────────────────┘    └─────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 一、sendText 文本发送流程

### 1.1 入口函数: sendWeixinOutbound

```typescript
// src/channel.ts
async function sendWeixinOutbound(params: {
  cfg: OpenClawConfig;
  to: string;                    // 目标用户 ID
  text: string;                  // 消息内容
  accountId?: string | null;
  contextToken?: string;         // 会话上下文令牌
  mediaUrl?: string;
}): Promise<{ channel: string; messageId: string }> {
  const account = resolveWeixinAccount(params.cfg, params.accountId);
  assertSessionActive(account.accountId);  // 检查 Session 状态

  if (!account.configured) {
    throw new Error("weixin not configured: please run `openclaw channels login --channel openclaw-weixin`");
  }

  if (!params.contextToken) {
    throw new Error("sendWeixinOutbound: contextToken is required");
  }

  const result = await sendMessageWeixin({
    to: params.to,
    text: params.text,
    opts: {
      baseUrl: account.baseUrl,
      token: account.token,
      contextToken: params.contextToken,
    }
  });
  return { channel: "openclaw-weixin", messageId: result.messageId };
}
```

### 1.2 核心函数: sendMessageWeixin

```typescript
// src/messaging/send.ts
export async function sendMessageWeixin(params: {
  to: string;
  text: string;
  opts: WeixinApiOptions & { contextToken?: string };
}): Promise<{ messageId: string }> {
  const { to, text, opts } = params;

  // 1. 验证 contextToken (必须)
  if (!opts.contextToken) {
    throw new Error("sendMessageWeixin: contextToken is required");
  }

  // 2. 生成客户端 ID
  const clientId = generateId("openclaw-weixin");

  // 3. 构建消息请求
  const req = buildSendMessageReq({
    to,
    contextToken: opts.contextToken,
    payload: { text: markdownToPlainText(text) },
    clientId,
  });

  // 4. 调用 API 发送
  await sendMessageApi({
    baseUrl: opts.baseUrl,
    token: opts.token,
    timeoutMs: opts.timeoutMs,
    body: req,
  });

  return { messageId: clientId };
}
```

### 1.3 Markdown 转纯文本

```typescript
// src/messaging/send.ts
export function markdownToPlainText(text: string): string {
  let result = text;
  // 代码块: 去掉围栏，保留代码内容
  result = result.replace(/```[^\n]*\n?([\s\S]*?)```/g, (_, code: string) => code.trim());
  // 图片: 完全移除
  result = result.replace(/!\[[^\]]*\]\([^)]*\)/g, "");
  // 链接: 只保留显示文本
  result = result.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
  // 表格: 移除分隔行，转换管道符为空格
  result = result.replace(/^\|[\s:|-]+\|$/gm, "");
  result = result.replace(/^\|(.+)\|$/gm, (_, inner: string) =>
    inner.split("|").map((cell) => cell.trim()).join("  "),
  );
  result = stripMarkdown(result);  // SDK 提供的通用 Markdown 剥离
  return result;
}
```

### 1.4 构建消息请求

```typescript
// src/messaging/send.ts
function buildTextMessageReq(params: {
  to: string;
  text: string;
  contextToken?: string;
  clientId: string;
}): SendMessageReq {
  const { to, text, contextToken, clientId } = params;
  const item_list: MessageItem[] = text
    ? [{ type: MessageItemType.TEXT, text_item: { text } }]
    : [];
  return {
    msg: {
      from_user_id: "",
      to_user_id: to,
      client_id: clientId,
      message_type: MessageType.BOT,
      message_state: MessageState.FINISH,
      item_list: item_list.length ? item_list : undefined,
      context_token: contextToken ?? undefined,
    },
  };
}
```

### 1.5 API 调用

```typescript
// src/api/api.ts
export async function sendMessage(
  params: WeixinApiOptions & { body: SendMessageReq }
): Promise<void> {
  await apiFetch({
    baseUrl: params.baseUrl,
    endpoint: "ilink/bot/sendmessage",
    body: JSON.stringify({ ...params.body, base_info: buildBaseInfo() }),
    token: params.token,
    timeoutMs: params.timeoutMs ?? DEFAULT_API_TIMEOUT_MS,  // 15s
    label: "sendMessage",
  });
}
```

### 1.6 文本发送流程图

```
┌─────────────────────────────────────────────────────────────┐
│                      sendText                                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. 解析账号配置 (resolveWeixinAccount)                       │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Session 状态检查 (assertSessionActive)                    │
│    - 检查是否被暂停 (isSessionPaused)                        │
│    - 如果被暂停，抛出错误                                    │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. 检查账号配置状态                                          │
│    - configured 必须为 true                                  │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. 验证 contextToken                                         │
│    - 必须存在，否则无法关联会话                               │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Markdown 转纯文本                                         │
│    - 代码块: 去围栏保留内容                                   │
│    - 图片: 完全移除                                           │
│    - 链接: 保留显示文本                                       │
│    - 表格: 转换管道符为空格                                   │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. 构建消息请求 (SendMessageReq)                             │
│    - client_id: 随机生成                                     │
│    - message_type: BOT (2)                                   │
│    - message_state: FINISH (2)                               │
│    - item_list: [{ type: TEXT, text_item: { text } }]        │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. 调用 sendMessage API                                      │
│    POST /ilink/bot/sendmessage                               │
│    - 超时: 15 秒                                             │
│    - 认证: Bearer <token>                                    │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. 返回结果                                                  │
│    { channel: "openclaw-weixin", messageId: clientId }       │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、sendMedia 媒体发送流程

### 2.1 入口函数: sendMedia

```typescript
// src/channel.ts
sendMedia: async (ctx) => {
  const account = resolveWeixinAccount(ctx.cfg, ctx.accountId);
  assertSessionActive(account.accountId);

  if (!account.configured) {
    throw new Error("weixin not configured...");
  }

  const mediaUrl = ctx.mediaUrl;

  // 本地文件或远程 URL
  if (mediaUrl && (isLocalFilePath(mediaUrl) || isRemoteUrl(mediaUrl))) {
    let filePath: string;
    if (isLocalFilePath(mediaUrl)) {
      filePath = resolveLocalPath(mediaUrl);
    } else {
      // 远程 URL: 先下载到临时目录
      filePath = await downloadRemoteImageToTemp(mediaUrl, MEDIA_OUTBOUND_TEMP_DIR);
    }

    const contextToken = getContextToken(account.accountId, ctx.to);
    return sendWeixinMediaFile({
      filePath,
      to: ctx.to,
      text: ctx.text ?? "",
      opts: { baseUrl: account.baseUrl, token: account.token, contextToken },
      cdnBaseUrl: account.cdnBaseUrl,
    });
  }

  // 没有媒体 URL，退化为文本发送
  return sendWeixinOutbound({...});
}
```

### 2.2 媒体发送核心: sendWeixinMediaFile

```typescript
// src/messaging/send-media.ts
export async function sendWeixinMediaFile(params: {
  filePath: string;
  to: string;
  text: string;
  opts: WeixinApiOptions & { contextToken?: string };
  cdnBaseUrl: string;
}): Promise<{ messageId: string }> {
  const { filePath, to, text, opts, cdnBaseUrl } = params;

  // 1. 根据 MIME 类型路由
  const mime = getMimeFromFilename(filePath);

  if (mime.startsWith("video/")) {
    // 视频文件
    const uploaded = await uploadVideoToWeixin({ filePath, toUserId: to, opts, cdnBaseUrl });
    return sendVideoMessageWeixin({ to, text, uploaded, opts });
  }

  if (mime.startsWith("image/")) {
    // 图片文件
    const uploaded = await uploadFileToWeixin({ filePath, toUserId: to, opts, cdnBaseUrl });
    return sendImageMessageWeixin({ to, text, uploaded, opts });
  }

  // 其他文件 (pdf, doc, zip 等)
  const fileName = path.basename(filePath);
  const uploaded = await uploadFileAttachmentToWeixin({
    filePath, fileName, toUserId: to, opts, cdnBaseUrl
  });
  return sendFileMessageWeixin({ to, text, fileName, uploaded, opts });
}
```

### 2.3 CDN 上传流程

```typescript
// src/cdn/upload.ts
async function uploadMediaToCdn(params: {
  filePath: string;
  toUserId: string;
  opts: WeixinApiOptions;
  cdnBaseUrl: string;
  mediaType: number;  // 1=IMAGE, 2=VIDEO, 3=FILE
  label: string;
}): Promise<UploadedFileInfo> {
  const { filePath, toUserId, opts, cdnBaseUrl, mediaType, label } = params;

  // 1. 读取文件
  const plaintext = await fs.readFile(filePath);
  const rawsize = plaintext.length;

  // 2. 计算 MD5
  const rawfilemd5 = crypto.createHash("md5").update(plaintext).digest("hex");

  // 3. 计算 AES-128-ECB 加密后大小 (PKCS7 填充)
  const filesize = aesEcbPaddedSize(rawsize);

  // 4. 生成随机 filekey 和 aeskey
  const filekey = crypto.randomBytes(16).toString("hex");
  const aeskey = crypto.randomBytes(16);

  // 5. 获取上传 URL
  const uploadUrlResp = await getUploadUrl({
    ...opts,
    filekey,
    media_type: mediaType,
    to_user_id: toUserId,
    rawsize,
    rawfilemd5,
    filesize,
    no_need_thumb: true,
    aeskey: aeskey.toString("hex"),
  });

  // 6. 上传文件到 CDN
  const { downloadParam: downloadEncryptedQueryParam } = await uploadBufferToCdn({
    buf: plaintext,
    uploadParam: uploadUrlResp.upload_param,
    filekey,
    cdnBaseUrl,
    aeskey,
    label,
  });

  // 7. 返回上传信息
  return {
    filekey,
    downloadEncryptedQueryParam,
    aeskey: aeskey.toString("hex"),
    fileSize: rawsize,
    fileSizeCiphertext: filesize,
  };
}
```

### 2.4 发送图片消息

```typescript
// src/messaging/send.ts
export async function sendImageMessageWeixin(params: {
  to: string;
  text: string;
  uploaded: UploadedFileInfo;
  opts: WeixinApiOptions & { contextToken?: string };
}): Promise<{ messageId: string }> {
  const { to, text, uploaded, opts } = params;

  // 验证 contextToken
  if (!opts.contextToken) {
    throw new Error("sendImageMessageWeixin: contextToken is required");
  }

  // 构建 ImageItem
  const imageItem: MessageItem = {
    type: MessageItemType.IMAGE,
    image_item: {
      media: {
        encrypt_query_param: uploaded.downloadEncryptedQueryParam,
        aes_key: Buffer.from(uploaded.aeskey).toString("base64"),
        encrypt_type: 1,
      },
      mid_size: uploaded.fileSizeCiphertext,
    },
  };

  // 发送 (支持文字说明)
  return sendMediaItems({ to, text, mediaItem: imageItem, opts, label: "sendImageMessageWeixin" });
}
```

### 2.5 发送视频消息

```typescript
// src/messaging/send.ts
export async function sendVideoMessageWeixin(params: {
  to: string;
  text: string;
  uploaded: UploadedFileInfo;
  opts: WeixinApiOptions & { contextToken?: string };
}): Promise<{ messageId: string }> {
  const { to, text, uploaded, opts } = params;

  if (!opts.contextToken) {
    throw new Error("sendVideoMessageWeixin: contextToken is required");
  }

  const videoItem: MessageItem = {
    type: MessageItemType.VIDEO,
    video_item: {
      media: {
        encrypt_query_param: uploaded.downloadEncryptedQueryParam,
        aes_key: Buffer.from(uploaded.aeskey).toString("base64"),
        encrypt_type: 1,
      },
      video_size: uploaded.fileSizeCiphertext,
    },
  };

  return sendMediaItems({ to, text, mediaItem: videoItem, opts, label: "sendVideoMessageWeixin" });
}
```

### 2.6 发送文件附件

```typescript
// src/messaging/send.ts
export async function sendFileMessageWeixin(params: {
  to: string;
  text: string;
  fileName: string;
  uploaded: UploadedFileInfo;
  opts: WeixinApiOptions & { contextToken?: string };
}): Promise<{ messageId: string }> {
  const { to, text, fileName, uploaded, opts } = params;

  if (!opts.contextToken) {
    throw new Error("sendFileMessageWeixin: contextToken is required");
  }

  const fileItem: MessageItem = {
    type: MessageItemType.FILE,
    file_item: {
      media: {
        encrypt_query_param: uploaded.downloadEncryptedQueryParam,
        aes_key: Buffer.from(uploaded.aeskey).toString("base64"),
        encrypt_type: 1,
      },
      file_name: fileName,
      len: String(uploaded.fileSize),  // 明文大小
    },
  };

  return sendMediaItems({ to, text, mediaItem: fileItem, opts, label: "sendFileMessageWeixin" });
}
```

### 2.7 媒体项发送辅助函数

```typescript
// src/messaging/send.ts
async function sendMediaItems(params: {
  to: string;
  text: string;
  mediaItem: MessageItem;
  opts: WeixinApiOptions & { contextToken?: string };
  label: string;
}): Promise<{ messageId: string }> {
  const { to, text, mediaItem, opts, label } = params;

  // 构建消息列表: 先发送文字说明(如果有)，再发送媒体
  const items: MessageItem[] = [];
  if (text) {
    items.push({ type: MessageItemType.TEXT, text_item: { text } });
  }
  items.push(mediaItem);

  // 逐个发送 (每个 item 单独一个请求)
  let lastClientId = "";
  for (const item of items) {
    lastClientId = generateId("openclaw-weixin");
    const req: SendMessageReq = {
      msg: {
        from_user_id: "",
        to_user_id: to,
        client_id: lastClientId,
        message_type: MessageType.BOT,
        message_state: MessageState.FINISH,
        item_list: [item],  // 每个请求只包含一个 item
        context_token: opts.contextToken ?? undefined,
      },
    };
    await sendMessageApi({ baseUrl: opts.baseUrl, token: opts.token, body: req });
  }

  return { messageId: lastClientId };
}
```

### 2.8 媒体发送完整流程图

```
┌─────────────────────────────────────────────────────────────┐
│                      sendMedia                               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. 解析账号配置和 Session 检查                                │
│    (同 sendText)                                             │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. 判断媒体来源                                              │
│    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│    │ 本地文件    │  │ 远程 URL    │  │ 无媒体      │        │
│    │ ./file.jpg  │  │ https://... │  │ (纯文本)    │        │
│    └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│           │                │                │               │
│           ▼                ▼                ▼               │
│    ┌──────────┐      ┌──────────┐      ┌──────────┐         │
│    │直接使用  │      │下载到本地│      │退化为    │         │
│    │文件路径  │      │临时目录  │      │sendText  │         │
│    └──────────┘      └────┬─────┘      └──────────┘         │
│                           │                                  │
└───────────────────────────┼──────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. MIME 类型路由 (sendWeixinMediaFile)                       │
│    ┌──────────────┬──────────────┬──────────────┐            │
│    │  video/*     │   image/*    │   其他       │            │
│    │   (视频)     │   (图片)     │ (pdf/zip等)  │            │
│    └──────┬───────┘──────┬───────┘──────┬───────┘            │
│           │              │              │                     │
│           ▼              ▼              ▼                     │
│    ┌──────────┐   ┌──────────┐   ┌──────────┐                │
│    │uploadVideo│   │uploadFile│   │uploadFile│                │
│    │ToWeixin  │   │ToWeixin  │   │Attachment│                │
│    └────┬─────┘   └────┬─────┘   └────┬─────┘                │
│         │              │              │                       │
└─────────┼──────────────┼──────────────┼───────────────────────┘
          │              │              │
          └──────────────┼──────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. CDN 上传流程 (uploadMediaToCdn)                           │
│    ┌──────────────────────────────────────────────────────┐  │
│    │ 4.1 读取文件内容                                      │  │
│    ├──────────────────────────────────────────────────────┤  │
│    │ 4.2 计算 MD5                                          │  │
│    ├──────────────────────────────────────────────────────┤  │
│    │ 4.3 计算 AES-128-ECB 加密后大小 (PKCS7 填充)          │  │
│    │     padded_size = ceil(rawsize/16) * 16               │  │
│    ├──────────────────────────────────────────────────────┤  │
│    │ 4.4 生成随机 filekey 和 aeskey                        │  │
│    ├──────────────────────────────────────────────────────┤  │
│    │ 4.5 调用 getUploadUrl 获取上传参数                    │  │
│    │     POST /ilink/bot/getuploadurl                      │  │
│    ├──────────────────────────────────────────────────────┤  │
│    │ 4.6 加密并上传文件到 CDN                              │  │
│    │     PUT <cdn_url> with AES-128-ECB encrypted data     │  │
│    ├──────────────────────────────────────────────────────┤  │
│    │ 4.7 返回 UploadedFileInfo                             │  │
│    └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. 构建并发送消息                                            │
│    ┌──────────────────────────────────────────────────────┐  │
│    │ 5.1 根据类型构建 MessageItem                          │  │
│    │     - ImageItem: media, mid_size                      │  │
│    │     - VideoItem: media, video_size                    │  │
│    │     - FileItem:  media, file_name, len                │  │
│    ├──────────────────────────────────────────────────────┤  │
│    │ 5.2 先发送文字说明(如果有)                            │  │
│    ├──────────────────────────────────────────────────────┤  │
│    │ 5.3 发送媒体项                                        │  │
│    │     POST /ilink/bot/sendmessage                       │  │
│    └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. 返回结果                                                  │
│    { channel: "openclaw-weixin", messageId: clientId }       │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、关键数据结构

### 3.1 UploadedFileInfo

```typescript
export type UploadedFileInfo = {
  filekey: string;                          // 文件标识符
  downloadEncryptedQueryParam: string;      // CDN 下载加密参数
  aeskey: string;                           // AES-128-ECB key (hex)
  fileSize: number;                         // 明文文件大小
  fileSizeCiphertext: number;               // 密文文件大小 (PKCS7 填充后)
};
```

### 3.2 SendMessageReq

```typescript
interface SendMessageReq {
  msg: {
    from_user_id: string;      // 发送者 ID (Bot 为空)
    to_user_id: string;        // 接收者 ID
    client_id: string;         // 客户端生成的消息 ID
    message_type: number;      // 1=USER, 2=BOT
    message_state: number;     // 0=NEW, 1=GENERATING, 2=FINISH
    item_list?: MessageItem[]; // 消息内容列表
    context_token?: string;    // 会话上下文令牌
  };
}
```

### 3.3 MessageItem 类型

```typescript
interface MessageItem {
  type: number;              // 1=TEXT, 2=IMAGE, 3=VOICE, 4=FILE, 5=VIDEO
  text_item?: { text: string };
  image_item?: {
    media?: CDNMedia;
    mid_size?: number;
  };
  video_item?: {
    media?: CDNMedia;
    video_size?: number;
  };
  file_item?: {
    media?: CDNMedia;
    file_name?: string;
    len?: string;
  };
}

interface CDNMedia {
  encrypt_query_param?: string;
  aes_key?: string;          // base64-encoded
  encrypt_type?: number;     // 1=打包缩略图信息
}
```

---

## 四、安全与加密

### 4.1 AES-128-ECB 加密

```typescript
// src/cdn/aes-ecb.ts
export function aesEcbEncrypt(plaintext: Buffer, key: Buffer): Buffer {
  const cipher = crypto.createCipheriv("aes-128-ecb", key, null);
  return Buffer.concat([cipher.update(plaintext), cipher.final()]);
}

export function aesEcbPaddedSize(rawSize: number): number {
  const blockSize = 16;
  const padding = blockSize - (rawSize % blockSize);
  return rawSize + (padding === blockSize ? 0 : padding);
}
```

### 4.2 上传流程安全

1. **本地生成密钥**: AES key 在本地随机生成，不上传
2. **端到端加密**: 文件使用 AES-128-ECB 加密后上传
3. **CDN 只存储密文**: 微信 CDN 只保存加密后的文件
4. **下载参数分离**: 下载时需要 `encrypt_query_param` 和 `aes_key` 组合

---

## 五、错误处理

| 错误场景 | 处理方式 |
|---------|---------|
| contextToken 缺失 | 抛出错误，拒绝发送 |
| Session 被暂停 | 抛出错误，提示剩余暂停时间 |
| 账号未配置 | 抛出错误，提示登录命令 |
| CDN 上传失败 | 抛出错误，记录日志 |
| API 调用超时 | 抛出错误，由上层重试 |
| 远程文件下载失败 | 抛出错误，发送错误通知 |

---

## 六、常量与配置

```typescript
// src/messaging/send.ts
textChunkLimit: 4000;  // 文本分块限制

// src/api/api.ts
const DEFAULT_API_TIMEOUT_MS = 15_000;       // API 调用超时
const DEFAULT_CONFIG_TIMEOUT_MS = 10_000;    // 配置请求超时

// src/channel.ts
const MEDIA_OUTBOUND_TEMP_DIR = "/tmp/openclaw/weixin/media/outbound-temp";
```

---

## 七、发送流程对比

| 特性 | sendText | sendMedia |
|-----|---------|-----------|
| 入口 | `sendWeixinOutbound` | `sendWeixinOutbound` 或 `sendWeixinMediaFile` |
| 预处理 | Markdown 转纯文本 | MIME 类型检测 |
| 网络请求 | 1 次 API 调用 | 2 次 API (getUploadUrl + sendMessage) + 1 次 CDN PUT |
| 加密 | 无 | AES-128-ECB |
| 文件存储 | 无 | 临时文件/内存 |
| 支持文字说明 | 否 | 是 (先发文字再发媒体) |
| 消息拆分 | 无 | 多个 MessageItem 单独发送 |
