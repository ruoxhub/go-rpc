package handler

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/client"
	"github.com/mrh30000/go-rpc/pkg/forwarder"
	"github.com/stretchr/testify/assert"
)

func TestRenderUnaryResponse_EnvelopeV2_DoesNotFlattenData(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := &APIHandler{}

	recorder := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(recorder)
	c.Request = httptest.NewRequest(http.MethodPost, "/business/invoke", nil)
	c.Request.Header.Set("x-envelope-version", "v2")

	targetClient := client.NewRpcClient("actual_group", "client-123", nil)
	respPayload := []byte(`{"group":"payload_group","items":[1,2,3]}`)
	invokeResp := &forwarder.InvokeResponse{
		Status: 0,
		Data:   respPayload,
	}

	h.renderUnaryResponse(c, &InvokeBuilder{}, "actual_group", targetClient, invokeResp, "testAction", time.Now())

	assert.Equal(t, http.StatusOK, recorder.Code)

	var result map[string]interface{}
	err := json.Unmarshal(recorder.Body.Bytes(), &result)
	assert.NoError(t, err)

	// 元信息必须保留为顶层真实值，不被 payload 覆盖
	assert.Equal(t, float64(0), result["code"])
	assert.Equal(t, "actual_group", result["group"])
	assert.Equal(t, "client-123", result["clientId"])

	// v2 信封要求：data 作为独立对象，且内部包含 payload 的字段
	dataObj, ok := result["data"].(map[string]interface{})
	assert.True(t, ok, "v2 模式下 data 必须为独立对象而不是被展开到顶层")
	assert.Equal(t, "payload_group", dataObj["group"])
	assert.Len(t, dataObj["items"], 3)
}
