/** 文档上传页面 */

import React, { useState } from 'react'
import {
  Button,
  Card,
  Space,
  Typography,
  message,
  Upload,
  Tag,
  Progress,
  Alert,
  Divider,
} from 'antd'
import {
  UploadOutlined,
  InboxOutlined,
  CheckCircleFilled,
  FileWordOutlined,
  DeleteOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import type { UploadProps, UploadFile } from 'antd'

import { useUploadStore } from '../../store'
import { uploadApi } from '../../api'
import type { DocumentResponse } from '../../types'
import styles from './UploadPage.module.css'

const { Text, Title } = Typography
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
  const progressPercent =
    status === 'success' ? 100 : status === 'uploading' ? 65 : status === 'error' ? 30 : 0

  const handleUpload: UploadProps['customRequest'] = async (options) => {
    const { file, onSuccess, onError } = options
    const realFile = file as File

    try {
      const result = await uploadApi.upload(realFile)
      const doc: DocumentResponse = result.document
      onSuccess?.(result)
      messageApi.success(`文件 ${realFile.name} 上传成功，文档ID: ${doc.id}`)
    } catch (err) {
      const error = err as Error
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
    const hasAllowedMime =
      file.type === '' || file.type === 'application/octet-stream' ? false : ALLOWED_TYPES.includes(file.type)

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
    <div className={styles.page}>
      {contextHolder}

      <header className={styles.header}>
        <div>
          <Title level={3} className={styles.title}>
            文档上传
          </Title>
          <p className={styles.subtitle}>上传 Word 报告，自动进入抽取流程并入图</p>
        </div>
        <Tag color="blue">8D Pipeline</Tag>
      </header>

      <div className={styles.grid}>
        <Card className={styles.mainCard} bordered={false}>
          <div className={styles.cardHead}>
            <Space>
              <FileWordOutlined style={{ color: '#1677ff' }} />
              <Text strong>上传 8D 报告文档</Text>
            </Space>
            <Text type="secondary">支持 Word（.doc / .docx）</Text>
          </div>
          <Divider style={{ margin: '12px 0' }} />

          <Dragger
            multiple={false}
            fileList={fileList}
            customRequest={handleUpload}
            onChange={handleChange}
            beforeUpload={handleBeforeUpload}
            accept=".doc,.docx"
            disabled={isUploading}
            style={{ borderRadius: 10 }}
            name="file"
            listType="text"
            showUploadList
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined style={{ fontSize: 48, color: '#1677ff' }} />
            </p>
            <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
            <p className="ant-upload-hint">单文件大小不超过 50MB</p>
          </Dragger>

          <div className={styles.actions}>
            <Button
              size="small"
              icon={<DeleteOutlined />}
              onClick={handleReset}
              disabled={fileList.length === 0 && status === 'idle'}
            >
              清空状态
            </Button>
            <Tag color={status === 'success' ? 'success' : status === 'error' ? 'error' : 'processing'}>
              当前状态：{status}
            </Tag>
          </div>

          {(status === 'uploading' || status === 'success' || status === 'error') && (
            <div className={styles.progressWrap}>
              <Progress
                percent={progressPercent}
                status={status === 'error' ? 'exception' : status === 'success' ? 'success' : 'active'}
                showInfo={false}
              />
            </div>
          )}

          {status === 'success' && uploadedDocument && (
            <Alert
              className={styles.alert}
              type="success"
              showIcon
              icon={<CheckCircleFilled />}
              message="上传成功"
              description={`文档ID: ${uploadedDocument.id}`}
            />
          )}

          {status === 'error' && (
            <Alert
              className={styles.alert}
              type="error"
              showIcon
              message="上传失败"
              description={errorMessage || '请稍后重试'}
            />
          )}
        </Card>

        <Card className={styles.sideCard} bordered={false}>
          <div className={styles.sideTitle}>
            <SafetyCertificateOutlined />
            <span>上传规范</span>
          </div>
          <ul className={styles.rules}>
            <li>仅支持 Word 文档：`.doc` / `.docx`</li>
            <li>单文件上限 50MB</li>
            <li>建议上传完整 8D 报告原文，避免分页截图</li>
            <li>上传后可前往抽取任务页查看进度</li>
          </ul>
          <Divider />
          <div className={styles.sideMeta}>
            <Text type="secondary">允许格式：{ALLOWED_EXTENSIONS.join(' / ')}</Text>
            <Text type="secondary">大小限制：50MB</Text>
          </div>
          <Button size="small" type="primary" icon={<UploadOutlined />} block disabled={fileList.length === 0}>
            文件已加入上传队列
          </Button>
        </Card>
      </div>
    </div>
  )
}

export default UploadPage
