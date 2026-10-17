package handler

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mrh30000/go-rpc/pkg/client"
	"github.com/mrh30000/go-rpc/pkg/database/repository"
	"github.com/mrh30000/go-rpc/pkg/middleware"
	"github.com/mrh30000/go-rpc/pkg/model"
	"github.com/stretchr/testify/assert"
)

type testGroupRepoForDevices struct {
	devices        []model.GroupDevice
	deletedOffline int64

	// 非 nil 时按 map 精确查找分组（nil 时按旧行为返回同名空分组）
	groups        map[string]*model.GroupConfig
	stats         []repository.GroupStats
	deletedGroups []string
	updatedGroups []string
	updatedQps    map[string]interface{}
}

func (m *testGroupRepoForDevices) FindDevicesByGroup(name string) ([]model.GroupDevice, error) {
	return m.devices, nil
}

func (m *testGroupRepoForDevices) DeleteOfflineDevicesByGroup(name string, before time.Time) (int64, error) {
	m.deletedOffline = int64(len(m.devices))
	m.devices = nil
	return m.deletedOffline, nil
}

func (m *testGroupRepoForDevices) FindDevice(groupName, deviceID string) (*model.GroupDevice, error) {
	for _, d := range m.devices {
		if d.GroupName == groupName && d.DeviceID == deviceID {
			return &d, nil
		}
	}
	return nil, nil
}

func (m *testGroupRepoForDevices) UpdateDevice(groupName, deviceID string, updates map[string]interface{}) error {
	return nil
}

func (m *testGroupRepoForDevices) EnsureGroup(groupName string, userName string) (*model.GroupConfig, error) {
	return &model.GroupConfig{GroupName: groupName}, nil
}
func (m *testGroupRepoForDevices) FindByName(name string) (*model.GroupConfig, error) {
	return &model.GroupConfig{GroupName: name}, nil
}
func (m *testGroupRepoForDevices) FindGroupByName(name string) (*model.GroupConfig, error) {
	if m.groups != nil {
		return m.groups[name], nil
	}
	return &model.GroupConfig{GroupName: name}, nil
}
func (m *testGroupRepoForDevices) FindAllGroups() ([]model.GroupConfig, error) {
	return nil, nil
}
func (m *testGroupRepoForDevices) Rollback() error {
	return nil
}
func (m *testGroupRepoForDevices) GetGroupStats(userName string, isAdmin bool, activeThreshold string) ([]repository.GroupStats, error) {
	if m.stats != nil {
		return m.stats, nil
	}
	return nil, nil
}
func (m *testGroupRepoForDevices) GetGroupDeviceStats(name string, activeThreshold string) (int64, int64, error) {
	return 0, 0, nil
}
func (m *testGroupRepoForDevices) CreateDevice(device *model.GroupDevice) error  { return nil }
func (m *testGroupRepoForDevices) DeleteDevice(groupName, deviceID string) error { return nil }
func (m *testGroupRepoForDevices) DeleteDevicesByGroup(name string) error        { return nil }
func (m *testGroupRepoForDevices) CountOnlineDevices(since string) (int64, error) {
	return 0, nil
}
func (m *testGroupRepoForDevices) CountDevicesByGroup(name string) (int64, error) {
	return 0, nil
}
func (m *testGroupRepoForDevices) FindActionsByGroup(name string) ([]model.GroupAction, error) {
	return nil, nil
}
func (m *testGroupRepoForDevices) FindAction(groupName, actionName string) (*model.GroupAction, error) {
	return nil, nil
}
func (m *testGroupRepoForDevices) CreateAction(action *model.GroupAction) error { return nil }
func (m *testGroupRepoForDevices) UpsertAction(action *model.GroupAction) error { return nil }
func (m *testGroupRepoForDevices) UpdateActionParams(groupName, actionName, actionParams string) error {
	return nil
}
func (m *testGroupRepoForDevices) DeleteAction(groupName, actionName string) error { return nil }
func (m *testGroupRepoForDevices) DeleteActionsByGroup(name string) error          { return nil }
func (m *testGroupRepoForDevices) IsGroupRegistered(name string) (bool, error)     { return true, nil }
func (m *testGroupRepoForDevices) EnsureDefaultActions(groupName string) error     { return nil }
func (m *testGroupRepoForDevices) UpsertDevice(device *model.GroupDevice) error    { return nil }
func (m *testGroupRepoForDevices) UpdateDeviceLastActive(groupName, deviceID string, t time.Time) error {
	return nil
}
func (m *testGroupRepoForDevices) WithTx(tx interface{}) repository.GroupRepository {
	return m
}
func (m *testGroupRepoForDevices) BeginTx() repository.GroupRepository {
	return m
}
func (m *testGroupRepoForDevices) Commit() error {
	return nil
}
func (m *testGroupRepoForDevices) CreateGroup(group *model.GroupConfig) error { return nil }
func (m *testGroupRepoForDevices) UpdateGroup(name string, updates map[string]interface{}) error {
	m.updatedGroups = append(m.updatedGroups, name)
	m.updatedQps = updates
	return nil
}
func (m *testGroupRepoForDevices) DeleteGroup(name string) error {
	m.deletedGroups = append(m.deletedGroups, name)
	return nil
}
func (m *testGroupRepoForDevices) CountGroups() (int64, error) {
	return 0, nil
}
func (m *testGroupRepoForDevices) ListGroups(page, pageSize int) ([]model.GroupConfig, int64, error) {
	return nil, 0, nil
}

func TestGroupHandler_GetDevices_RealOnlineStatus(t *testing.T) {
	gin.SetMode(gin.TestMode)

	cm := client.NewClientManager()
	onlineCli := client.NewRpcClient("twitter", "online-client-1", nil)
	onlineCli.SetStatus(client.StatusOnline)
	cm.Register(onlineCli)

	repo := &testGroupRepoForDevices{
		devices: []model.GroupDevice{
			{
				GroupName:      "twitter",
				DeviceID:       "online-client-1",
				RemoteIP:       "127.0.0.1",
				CreateDate:     time.Now().Add(-1 * time.Hour),
				LastActiveTime: time.Now().Add(-1 * time.Minute),
			},
			{
				GroupName:      "twitter",
				DeviceID:       "offline-client-2",
				RemoteIP:       "127.0.0.1",
				CreateDate:     time.Now().Add(-2 * time.Hour),
				LastActiveTime: time.Now().Add(-1 * time.Minute), // 最近刚活跃，但WS已断开
			},
		},
	}

	h := NewGroupHandler(repo, nil, cm)

	router := gin.New()
	router.Use(func(c *gin.Context) {
		c.Set(middleware.ContextUserKey, &model.UserInfo{UserName: "admin", IsAdmin: true})
		c.Next()
	})
	router.GET("/groups/:groupName/devices", h.GetDevices)

	req := httptest.NewRequest(http.MethodGet, "/groups/twitter/devices", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)

	var resp struct {
		Code int            `json:"code"`
		Data []DeviceInfoVO `json:"data"`
	}
	err := json.Unmarshal(w.Body.Bytes(), &resp)
	assert.NoError(t, err)
	assert.Len(t, resp.Data, 1)

	assert.Equal(t, "online-client-1", resp.Data[0].DeviceID)
	assert.Equal(t, "online", resp.Data[0].Status)
}

// newBatchTestRouter 构造带登录用户的批量操作测试路由。
func newBatchTestRouter(h *GroupHandler, user *model.UserInfo) *gin.Engine {
	router := gin.New()
	router.Use(func(c *gin.Context) {
		c.Set(middleware.ContextUserKey, user)
		c.Next()
	})
	router.POST("/groups/batch/delete", h.BatchDelete)
	router.PUT("/groups/batch/qps", h.BatchUpdateQps)
	return router
}

func doBatchJSON(t *testing.T, router *gin.Engine, method, path string, body interface{}) *httptest.ResponseRecorder {
	t.Helper()
	raw, err := json.Marshal(body)
	assert.NoError(t, err)
	req := httptest.NewRequest(method, path, bytes.NewReader(raw))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)
	return w
}

type batchResp struct {
	Code int              `json:"code"`
	Data BatchGroupResult `json:"data"`
}

func TestGroupHandler_BatchDelete_PartialFailure(t *testing.T) {
	gin.SetMode(gin.TestMode)

	repo := &testGroupRepoForDevices{groups: map[string]*model.GroupConfig{
		"g1": {GroupName: "g1", UserName: "alice"},
	}}
	h := NewGroupHandler(repo, nil, nil)
	router := newBatchTestRouter(h, &model.UserInfo{UserName: "alice", IsAdmin: true})

	w := doBatchJSON(t, router, http.MethodPost, "/groups/batch/delete", map[string]interface{}{
		"groupNames": []string{"g1", "missing"},
	})

	assert.Equal(t, http.StatusOK, w.Code)
	var resp batchResp
	assert.NoError(t, json.Unmarshal(w.Body.Bytes(), &resp))
	assert.Equal(t, []string{"g1"}, resp.Data.Succeeded)
	assert.Len(t, resp.Data.Failed, 1)
	assert.Equal(t, "missing", resp.Data.Failed[0].GroupName)
	assert.Contains(t, resp.Data.Failed[0].Reason, "not found")
	assert.Equal(t, []string{"g1"}, repo.deletedGroups)
}

func TestGroupHandler_BatchDelete_DeniesOtherUsersGroup(t *testing.T) {
	gin.SetMode(gin.TestMode)

	repo := &testGroupRepoForDevices{groups: map[string]*model.GroupConfig{
		"mine":  {GroupName: "mine", UserName: "alice"},
		"other": {GroupName: "other", UserName: "bob"},
	}}
	h := NewGroupHandler(repo, nil, nil)
	router := newBatchTestRouter(h, &model.UserInfo{UserName: "alice"})

	w := doBatchJSON(t, router, http.MethodPost, "/groups/batch/delete", map[string]interface{}{
		"groupNames": []string{"mine", "other"},
	})

	assert.Equal(t, http.StatusOK, w.Code)
	var resp batchResp
	assert.NoError(t, json.Unmarshal(w.Body.Bytes(), &resp))
	assert.Equal(t, []string{"mine"}, resp.Data.Succeeded)
	assert.Len(t, resp.Data.Failed, 1)
	assert.Equal(t, "other", resp.Data.Failed[0].GroupName)
	assert.Equal(t, "无权访问该分组", resp.Data.Failed[0].Reason)
	assert.Equal(t, []string{"mine"}, repo.deletedGroups)
}

func TestGroupHandler_BatchDelete_RejectsEmptyGroupNames(t *testing.T) {
	gin.SetMode(gin.TestMode)

	repo := &testGroupRepoForDevices{}
	h := NewGroupHandler(repo, nil, nil)
	router := newBatchTestRouter(h, &model.UserInfo{UserName: "alice", IsAdmin: true})

	w := doBatchJSON(t, router, http.MethodPost, "/groups/batch/delete", map[string]interface{}{
		"groupNames": []string{},
	})

	assert.Equal(t, http.StatusBadRequest, w.Code)
	assert.Empty(t, repo.deletedGroups)
}

func TestGroupHandler_BatchUpdateQps_AppliesOnlyProvidedFields(t *testing.T) {
	gin.SetMode(gin.TestMode)

	repo := &testGroupRepoForDevices{groups: map[string]*model.GroupConfig{
		"g1": {GroupName: "g1", UserName: "alice"},
		"g2": {GroupName: "g2", UserName: "alice"},
	}}
	h := NewGroupHandler(repo, nil, nil)
	router := newBatchTestRouter(h, &model.UserInfo{UserName: "alice", IsAdmin: true})

	w := doBatchJSON(t, router, http.MethodPut, "/groups/batch/qps", map[string]interface{}{
		"groupNames":    []string{"g1", "g2", "g2"},
		"quotaQpsGroup": 50.0,
	})

	assert.Equal(t, http.StatusOK, w.Code)
	var resp batchResp
	assert.NoError(t, json.Unmarshal(w.Body.Bytes(), &resp))
	assert.Equal(t, []string{"g1", "g2"}, resp.Data.Succeeded)
	assert.Empty(t, resp.Data.Failed)
	assert.Equal(t, []string{"g1", "g2"}, repo.updatedGroups)
	_, hasGroupQps := repo.updatedQps["quota_qps_group"]
	assert.True(t, hasGroupQps)
	_, hasDeviceQps := repo.updatedQps["quota_qps_per_device"]
	assert.False(t, hasDeviceQps)
}

func TestGroupHandler_BatchUpdateQps_RejectsNoQpsField(t *testing.T) {
	gin.SetMode(gin.TestMode)

	repo := &testGroupRepoForDevices{groups: map[string]*model.GroupConfig{
		"g1": {GroupName: "g1", UserName: "alice"},
	}}
	h := NewGroupHandler(repo, nil, nil)
	router := newBatchTestRouter(h, &model.UserInfo{UserName: "alice", IsAdmin: true})

	w := doBatchJSON(t, router, http.MethodPut, "/groups/batch/qps", map[string]interface{}{
		"groupNames": []string{"g1"},
	})

	assert.Equal(t, http.StatusBadRequest, w.Code)
	assert.Empty(t, repo.updatedGroups)
}

func TestGroupHandler_Delete_RemovesCascade(t *testing.T) {
	gin.SetMode(gin.TestMode)

	repo := &testGroupRepoForDevices{groups: map[string]*model.GroupConfig{
		"g1": {GroupName: "g1", UserName: "alice"},
	}}
	h := NewGroupHandler(repo, nil, nil)

	router := gin.New()
	router.Use(func(c *gin.Context) {
		c.Set(middleware.ContextUserKey, &model.UserInfo{UserName: "alice", IsAdmin: true})
		c.Next()
	})
	router.DELETE("/groups", h.Delete)

	w := doBatchJSON(t, router, http.MethodDelete, "/groups", map[string]interface{}{"groupName": "g1"})

	assert.Equal(t, http.StatusOK, w.Code)
	assert.Equal(t, []string{"g1"}, repo.deletedGroups)
}

func TestGroupHandler_List_AvailableClients_FromClientManager(t *testing.T) {
	gin.SetMode(gin.TestMode)

	cm := client.NewClientManager()
	onlineCli := client.NewRpcClient("bilibili", "client-1", nil)
	onlineCli.SetStatus(client.StatusOnline)
	cm.Register(onlineCli)

	repo := &testGroupRepoForDevices{
		stats: []repository.GroupStats{
			{
				ID:               1,
				GroupName:        "bilibili",
				UserName:         "alice",
				AvailableClients: 0, // DB 统计为 0
				DisabledClients:  2,
			},
		},
	}
	h := NewGroupHandler(repo, nil, cm)

	router := gin.New()
	router.Use(func(c *gin.Context) {
		c.Set(middleware.ContextUserKey, &model.UserInfo{UserName: "alice", IsAdmin: true})
		c.Next()
	})
	router.GET("/groups", h.List)

	req := httptest.NewRequest(http.MethodGet, "/groups", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	var resp struct {
		Code int           `json:"code"`
		Data []GroupInfoVO `json:"data"`
	}
	assert.NoError(t, json.Unmarshal(w.Body.Bytes(), &resp))
	assert.Len(t, resp.Data, 1)
	// 即使 DB 为 0，实时 ClientManager 在线客户端也应当正确反映到可用客户端数量中
	assert.Equal(t, int64(1), resp.Data[0].AvailableClients)

	// 当客户端断开注销后，可用客户端数量立即变为 0，不受 DB 旧缓存影响
	cm.Unregister("bilibili", "client-1")
	w2 := httptest.NewRecorder()
	req2 := httptest.NewRequest(http.MethodGet, "/groups", nil)
	router.ServeHTTP(w2, req2)
	assert.Equal(t, http.StatusOK, w2.Code)
	var resp2 struct {
		Code int           `json:"code"`
		Data []GroupInfoVO `json:"data"`
	}
	assert.NoError(t, json.Unmarshal(w2.Body.Bytes(), &resp2))
	assert.Len(t, resp2.Data, 1)
	assert.Equal(t, int64(0), resp2.Data[0].AvailableClients)
}

func TestGroupHandler_GetDetail_AvailableClients_FromClientManager(t *testing.T) {
	gin.SetMode(gin.TestMode)

	cm := client.NewClientManager()
	onlineCli := client.NewRpcClient("bilibili", "client-1", nil)
	onlineCli.SetStatus(client.StatusOnline)
	cm.Register(onlineCli)

	repo := &testGroupRepoForDevices{
		groups: map[string]*model.GroupConfig{
			"bilibili": {
				GroupName:  "bilibili",
				UserName:   "alice",
				CreateDate: time.Now(),
			},
		},
	}
	h := NewGroupHandler(repo, nil, cm)

	router := gin.New()
	router.Use(func(c *gin.Context) {
		c.Set(middleware.ContextUserKey, &model.UserInfo{UserName: "alice", IsAdmin: true})
		c.Next()
	})
	router.GET("/groups/:groupName", h.GetDetail)

	req := httptest.NewRequest(http.MethodGet, "/groups/bilibili", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	assert.Equal(t, http.StatusOK, w.Code)
	var resp struct {
		Code int                    `json:"code"`
		Data map[string]interface{} `json:"data"`
	}
	assert.NoError(t, json.Unmarshal(w.Body.Bytes(), &resp))
	assert.Equal(t, float64(1), resp.Data["availableClients"])

	// 断开后查询详情立即为 0
	cm.Unregister("bilibili", "client-1")
	w2 := httptest.NewRecorder()
	req2 := httptest.NewRequest(http.MethodGet, "/groups/bilibili", nil)
	router.ServeHTTP(w2, req2)
	assert.Equal(t, http.StatusOK, w2.Code)
	var resp2 struct {
		Code int                    `json:"code"`
		Data map[string]interface{} `json:"data"`
	}
	assert.NoError(t, json.Unmarshal(w2.Body.Bytes(), &resp2))
	assert.Equal(t, float64(0), resp2.Data["availableClients"])
}

