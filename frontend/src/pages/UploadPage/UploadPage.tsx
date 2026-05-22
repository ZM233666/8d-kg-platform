/** 文档上传页面 */

import React, { useState } from 'react'
import {
  Button,
  Card,
  Space,
  Typography,
  message,
  Breadcrumb,
  Upload,
} from 'antd'
import { UploadOutlined, InboxOutlined, RestOutlined, CheckCircleFilled } from '@ant-design/icons'
import type { UploadProps, UploadFile } from 'antd'

import { useUploadStore } from '../../store'
import { uploadApi } from '../../api'
import type { DocumentResponse } from '../../types'

const { Text } = Typography
const { Dragger } = Upload

const ALLOWED_TYPES = [
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/msword',
]
const ALLOWED_EXTENSIONS = ['.doc', '.docx']

const MAX_SIZE = 50 * 1024 * 1024 // 50MB

export const UploadPage: React.FC = () => {
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const { status, uploadedDocument, errorMessage, resetUpload } = useUploadStore()
  const [messageApi, contextHolder] = message.useMessage()

  const isUploading = status === 'uploading'

  const handleUpload: UploadProps['customRequest'] = async (options) => {
    const { file, onSuccess, onError } = options
    const realFile = file as File

    try {
      const result = await uploadApi.upload(realFile)
      console.log('[Upload] success response:', result)
      const doc: DocumentResponse = result.document
      onSuccess?.(result)
      messageApi.success(`文件 ${realFile.name} 上传成功，文档ID: ${doc.id}`)
    } catch (err) {
      const error = err as Error
      const axiosErr = err as { response?: { data?: unknown; status?: number } }
      console.error('[Upload] error:', {
        message: error.message,
        status: axiosErr.response?.status,
        data: axiosErr.response?.data,
      })
      onError?.(error)
      messageApi.error(`上传失败: ${error.message}`)
    }
  }

  const handleChange: UploadProps['onChange'] = ({ fileList: newList }) => {
    setFileList(newList)
  }

  const handleBeforeUpload: UploadProps['beforeUpload'] = (file) => {
    const lowerName = file.name.toLowerCase()
    const hasAllowedExtension = ALLOWED_EXTENSIONS.some((ext) => lowerName.endsWith(ext))
    const hasAllowedMime = file.type === '' || file.type === 'application/octet-stream'
      ? false
      : ALLOWED_TYPES.includes(file.type)

    if (!hasAllowedExtension && !hasAllowedMime) {
      messageApi.error(`${file.name} 格式不支持，仅支持 Word（.doc / .docx）`)
      return false
    }
    if (file.size > MAX_SIZE) {
      messageApi.error(`${file.name} 超过 50MB 限制`)
      return false
    }
    return true
  }

  const handleReset = () => {
    setFileList([])
    resetUpload()
    messageApi.info('已重置')
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      {contextHolder}

      {/* 面包屑 */}
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[
          { title: '首页' },
          { title: '文档管理' },
          { title: '上传文档' },
        ]}
      />

      <Card
        title="上传 8D 报告文档"
        extra={<Text type="secondary">支持 Word（.doc / .docx），单文件≤50MB</Text>}
        style={{ borderRadius: 8 }}
      >
        {/* 文件上传区域 */}
        <Dragger
          multiple
          fileList={fileList}
          customRequest={handleUpload}
          onChange={handleChange}
          beforeUpload={handleBeforeUpload}
          accept=".doc,.docx"
          disabled={isUploading}
          style={{ borderRadius: 8 }}
          props={{
            name: 'file',
            listType: 'text',
            showUploadList: true,
            itemRender: (originNode, file) => (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 12px',
                  background: '#f5f5f5',
                  borderRadius: 6,
                  marginBottom: 4,
                }}
              >
                <span>{file.name}</span>
                {file.status === 'success' && <CheckCircleFilled style={{ color: '#52c41a' }} />}
              </div>
            ),
          }}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined style={{ fontSize: 48, color: '#1677ff' }} />
          </p>
          <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
          <p className="ant-upload-hint">支持 Word（.doc / .docx）格式</p>
        </Dragger>

        {/* 成功提示 */}
        {status === 'success' && uploadedDocument && (
          <Card size="small" style={{ background: '#f6ffed', marginTop: 16 }}>
            <Space>
              <CheckCircleFilled style={{ color: '#52c41a', fontSize: 20 }} />
              <Text strong>上传成功</Text>
              <Text type="secondary">文档ID: {uploadedDocument.id}</Text>
            </Space>
          </Card>
        )}

        {/* 错误提示 */}
        {status === 'error' && (
          <Card size="small" style={{ background: '#fff2f0', marginTop: 16 }}>
            <Text type="danger">上传失败: {errorMessage}</Text>
          </Card>
        )}

        {/* 按钮组 */}
        <div style={{ marginTop: 16 }}>
          <Space>
            <Button
              type="primary"
              icon={<UploadOutlined />}
              danger
              onClick={handleReset}
            >
              清空
            </Button>
          </Space>
        </div>
      </Card>
    </div>
  )
}

export default UploadPage
